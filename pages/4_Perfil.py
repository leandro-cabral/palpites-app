import streamlit as st
from database import get_connection, init_db
from utils import sidebar_login, avatar_url, AVATAR_STYLES

st.set_page_config(page_title="Perfil", page_icon="👤", layout="wide")

init_db()

with st.sidebar:
    st.title("⚽ Palpites")
    st.caption("Sistema de palpites para amigos")

usuario = sidebar_login()

st.title("👤 Perfil")

if not usuario:
    st.info("Faça login na barra lateral para acessar seu perfil.")
    st.stop()

conn = get_connection()
row  = conn.execute("SELECT saldo_moedas, avatar_style FROM usuarios WHERE nome=?", (usuario,)).fetchone()
conn.close()

saldo        = row["saldo_moedas"] if row else 10
style_atual  = row["avatar_style"] if row and row["avatar_style"] else "avataaars"

# ── Avatar atual ──────────────────────────────────────────────────────────────
col_avatar, col_info = st.columns([1, 3])
with col_avatar:
    st.image(avatar_url(usuario, style_atual, 120), width=120)

with col_info:
    st.markdown(f"### {usuario}")
    st.markdown(f"🪙 **Saldo de moedas:** {saldo}")

st.divider()

# ── Escolha de avatar ─────────────────────────────────────────────────────────
st.subheader("Escolher avatar")
st.caption("Cada estilo gera um avatar único baseado no seu nome.")

cols = st.columns(len(AVATAR_STYLES))
for col, (label, style) in zip(cols, AVATAR_STYLES.items()):
    with col:
        st.image(avatar_url(usuario, style, 80), width=80)
        selecionado = style == style_atual
        btn_label   = f"✅ {label}" if selecionado else label
        if st.button(btn_label, key=f"btn_{style}", use_container_width=True, disabled=selecionado):
            conn = get_connection()
            conn.execute("UPDATE usuarios SET avatar_style=? WHERE nome=?", (style, usuario))
            conn.commit()
            conn.close()
            st.rerun()

st.divider()

# ── Histórico do usuário ──────────────────────────────────────────────────────
st.subheader("Meus palpites")

conn    = get_connection()
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
    for p in palpites:
        resultado = (
            f"{p['gols_casa_real']}x{p['gols_fora_real']}"
            if p["gols_casa_real"] is not None else "Aguardando"
        )

        pts_badge = ""
        if p["pontos"] is not None:
            cores = {3: "🟢", 2: "🟡", 1: "🟠", 0: "🔴"}
            pts_badge = f"{cores.get(p['pontos'], '')} **{p['pontos']} pts**"

        moeda_info = ""
        if p["moeda_apostada"]:
            odd_txt = f" (odd {p['odd_apostada']:.2f})" if p["odd_apostada"] else ""
            if p["moedas_ganhas"] is not None:
                sinal = "+" if p["moedas_ganhas"] > 0 else ""
                moeda_info = f" | 🪙 {sinal}{p['moedas_ganhas']}{odd_txt}"
            else:
                moeda_info = f" | 🪙 em jogo{odd_txt}"

        st.markdown(
            f"**{p['jogo']}**  \n"
            f"Palpite: `{p['palpite_casa']}x{p['palpite_fora']}` · "
            f"Resultado: `{resultado}` · {pts_badge}{moeda_info}"
        )
