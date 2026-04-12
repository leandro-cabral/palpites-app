import streamlit as st
from database import get_connection, init_db
from scoring import fmt_ec
from utils import sidebar_login, get_avatar, AVATARES, _info_ec, apply_mobile_css

st.set_page_config(page_title="Perfil", page_icon="👤", layout="wide")

init_db()
apply_mobile_css()

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

st.title("👤 Perfil")

if not usuario:
    st.info("Faça login na barra lateral para acessar seu perfil.")
    st.stop()

saldo_total, em_jogo = _info_ec(usuario)
saldo  = max(saldo_total, 0)
avatar = get_avatar(usuario)

# ── Avatar atual ──────────────────────────────────────────────────────────────
col_av, col_info = st.columns([1, 4])
with col_av:
    st.markdown(
        f"<div style='font-size:80px;text-align:center;padding-top:10px'>{avatar}</div>",
        unsafe_allow_html=True,
    )
with col_info:
    st.markdown(f"### {usuario}")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("💰 Disponível", f"{saldo:.2f} EC")
    col_s2.metric("Em jogo", f"{em_jogo:.2f} EC")

st.divider()

# ── Escolha de avatar ─────────────────────────────────────────────────────────
st.subheader("Escolher avatar")

cols = st.columns(8)
for i, emoji in enumerate(AVATARES):
    with cols[i % 8]:
        selecionado = emoji == avatar
        label = f"{emoji}" + (" ✅" if selecionado else "")
        if st.button(
            label, key=f"av_{i}",
            use_container_width=True,
            type="primary" if selecionado else "secondary",
        ):
            conn = get_connection()
            conn.execute("UPDATE usuarios SET avatar_style=? WHERE nome=?", (emoji, usuario))
            conn.commit()
            conn.close()
            st.rerun()

st.divider()

# ── Histórico ─────────────────────────────────────────────────────────────────
st.subheader("Meus palpites")

conn     = get_connection()
palpites = conn.execute("""
    SELECT jogo, liga, palpite_casa, palpite_fora,
           gols_casa_real, gols_fora_real, pontos,
           moeda_apostada, odd_apostada, moedas_ganhas
    FROM palpites WHERE usuario=? ORDER BY id DESC
""", (usuario,)).fetchall()
conn.close()

if not palpites:
    st.info("Você ainda não fez nenhum palpite.")
else:
    cores_pts = {3: "🟢", 2: "🟡", 1: "🟠", 0: "🔴"}
    for p in palpites:
        resultado = (
            f"{p['gols_casa_real']}x{p['gols_fora_real']}"
            if p["gols_casa_real"] is not None else "Aguardando"
        )
        pts_badge = f"{cores_pts.get(p['pontos'],'')} **{p['pontos']} pts**" if p["pontos"] is not None else ""

        ec_info = ""
        if p["moeda_apostada"]:
            odd_txt = f" (odd {p['odd_apostada']:.2f})" if p["odd_apostada"] else ""
            if p["moedas_ganhas"] is not None:
                ec_info = f" · 💰 {fmt_ec(p['moedas_ganhas'])}{odd_txt}"
            else:
                ec_info = f" · 💰 {p['moeda_apostada']:.2f} EC em jogo{odd_txt}"

        st.markdown(
            f"**{p['jogo']}**  \n"
            f"Palpite: `{p['palpite_casa']}x{p['palpite_fora']}` · "
            f"Resultado: `{resultado}` {pts_badge}{ec_info}"
        )
