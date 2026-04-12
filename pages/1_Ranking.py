import streamlit as st
import pandas as pd
from database import get_connection, init_db
from utils import sidebar_login, get_avatar, apply_mobile_css
from scoring import DESCRICAO_PONTOS, calcular_score_ranking, ordenar_ranking
from api import get_liga_logos

st.set_page_config(page_title="Ranking Lisan Al Gaib", page_icon="🏆", layout="wide")

init_db()
apply_mobile_css()

@st.cache_data(ttl=86400)
def _logos_ligas():
    return get_liga_logos()

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

usuario_logado = sidebar_login()

st.title("🏆 Ranking Lisan Al Gaib")

conn = get_connection()

# ── Ranking geral ─────────────────────────────────────────────────────────────
rows = conn.execute("""
    SELECT
        p.usuario,
        COALESCE(MAX(u.saldo_ec), 10) AS saldo_ec,
        COALESCE((
            SELECT SUM(moeda_apostada) FROM palpites
            WHERE usuario = p.usuario AND moeda_apostada > 0 AND pontos IS NULL
        ), 0) AS ec_em_jogo,
        COUNT(*) AS total_palpites,
        SUM(CASE WHEN p.pontos IS NOT NULL THEN 1 ELSE 0 END) AS jogos_avaliados,
        COALESCE(SUM(p.pontos), 0) AS total_pontos,
        SUM(CASE WHEN p.pontos IN (4.5, 9.0) THEN 1 ELSE 0 END) AS placares_exatos,
        SUM(CASE WHEN p.pontos IN (3.0, 6.0) THEN 1 ELSE 0 END) AS empates_certos,
        SUM(CASE WHEN p.pontos = 1.5 THEN 1 ELSE 0 END) AS resultados_certos,
        SUM(CASE WHEN p.pontos < 0 THEN 1 ELSE 0 END) AS erros,
        SUM(CASE WHEN p.moeda_apostada > 0 AND p.pontos IS NOT NULL THEN 1 ELSE 0 END) AS apostas_resolvidas,
        COALESCE(SUM(p.moedas_ganhas), 0) AS ec_ganhos_total
    FROM palpites p
    LEFT JOIN usuarios u ON p.usuario = u.nome
    WHERE p.moeda_apostada > 0
    GROUP BY p.usuario
""").fetchall()

if not rows:
    st.info("Nenhum palpite registrado ainda.")
    conn.close()
    st.stop()

# Calcula score e ordena
dados = []
for r in rows:
    saldo_disp = max(float(r["saldo_ec"]) - float(r["ec_em_jogo"]), 0)
    score      = calcular_score_ranking(r["total_pontos"], r["saldo_ec"], r["ec_em_jogo"])
    dados.append({**dict(r), "saldo_disponivel": saldo_disp, "score": score})

dados = ordenar_ranking(dados)

# Tabela de ranking
df = pd.DataFrame(dados)
df["avatar"]  = df["usuario"].apply(get_avatar)
df["Jogador"] = df["avatar"] + " " + df["usuario"]
df.index      = range(1, len(df) + 1)
df.index.name = "Pos"

df_display = df[["Jogador", "score", "total_pontos", "saldo_disponivel",
                  "jogos_avaliados", "placares_exatos", "empates_certos",
                  "resultados_certos", "erros", "ec_ganhos_total"]].rename(columns={
    "score":             "⭐ Score",
    "total_pontos":      "Pts",
    "saldo_disponivel":  "💰 Banca",
    "jogos_avaliados":   "Avaliados",
    "placares_exatos":   "Exatos (3pts)",
    "empates_certos":    "Empates (2pts)",
    "resultados_certos": "Vencedor (1pt)",
    "erros":             "Erros",
    "ec_ganhos_total":   "💰 EC Ganhos",
})

# Destaque para o líder
lider = df_display.iloc[0]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Líder", lider["Jogador"])
col2.metric("⭐ Score", f"{lider['⭐ Score']:.1f}")
col3.metric("Pts", int(lider["Pts"]))
col4.metric("💰 Banca", f"{lider['💰 Banca']:.2f} EC")

st.caption("Score = Pontos × Banca disponível em EC")
st.divider()
st.dataframe(df_display, use_container_width=True)

# ── Detalhes por jogador ──────────────────────────────────────────────────────
st.subheader("Detalhes por jogador")

jogadores = [r["usuario"] for r in dados]
jogador_sel = st.selectbox("Selecionar jogador", jogadores)

palpites = conn.execute("""
    SELECT jogo, liga, palpite_casa, palpite_fora,
           gols_casa_real, gols_fora_real, pontos,
           moeda_apostada, moedas_ganhas, odd_apostada
    FROM palpites
    WHERE usuario = ? AND moeda_apostada > 0
    ORDER BY id DESC
""", (jogador_sel,)).fetchall()

if palpites:
    logos_ligas = _logos_ligas()

    # Agrupa palpites por liga
    por_liga = {}
    for p in palpites:
        liga = p["liga"] or "—"
        por_liga.setdefault(liga, []).append(p)

    for liga_nome, ps in por_liga.items():
        # Cabeçalho da liga com logo
        col_logo, col_nome = st.columns([0.3, 5])
        logo_url = logos_ligas.get(liga_nome, "")
        if logo_url:
            col_logo.image(logo_url, width=32)
        col_nome.markdown(f"**{liga_nome}**")

        rows_detail = []
        for p in ps:
            resultado_real = (
                f"{p['gols_casa_real']}x{p['gols_fora_real']}"
                if p["gols_casa_real"] is not None else "—"
            )
            odd_txt = f"{p['odd_apostada']:.2f}" if p["odd_apostada"] else "—"
            ec_txt  = (
                f"{p['moedas_ganhas']:+.2f}" if p["moedas_ganhas"] is not None
                else f"{p['moeda_apostada']:.2f} em jogo"
            )
            rows_detail.append({
                "Jogo":        p["jogo"],
                "Palpite":     f"{p['palpite_casa']}x{p['palpite_fora']}",
                "Resultado":   resultado_real,
                "Pts":         p["pontos"] if p["pontos"] is not None else "—",
                "Status":      DESCRICAO_PONTOS.get(p["pontos"], "Aguardando") if p["pontos"] is not None else "Aguardando",
                "EC apostado": f"{p['moeda_apostada']:.2f}",
                "Odd":         odd_txt,
                "EC resultado": ec_txt,
            })

        st.dataframe(pd.DataFrame(rows_detail), use_container_width=True, hide_index=True)
else:
    st.info("Nenhum palpite com EC encontrado.")

conn.close()
