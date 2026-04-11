import streamlit as st
from database import get_connection

AVATARES = [
    "⚽", "🏆", "👑", "🔥", "⚡", "🎯", "💎", "🌟",
    "🦁", "🐯", "🦊", "🐺", "🦅", "🦈", "🐊", "🦝",
    "🤠", "😎", "🥷", "🤖", "👾", "🎭", "🧙", "🏴‍☠️",
]

DEFAULT_AVATAR = "⚽"


def _info_moedas(usuario):
    conn    = get_connection()
    row     = conn.execute("SELECT saldo_moedas FROM usuarios WHERE nome=?", (usuario,)).fetchone()
    em_jogo = conn.execute(
        "SELECT COUNT(*) as c FROM palpites WHERE usuario=? AND moeda_apostada=1 AND pontos IS NULL",
        (usuario,),
    ).fetchone()["c"]
    conn.close()
    return (row["saldo_moedas"] if row else 10), em_jogo


def get_avatar(usuario):
    conn = get_connection()
    row  = conn.execute("SELECT avatar_style FROM usuarios WHERE nome=?", (usuario,)).fetchone()
    conn.close()
    style = row["avatar_style"] if row and row["avatar_style"] else DEFAULT_AVATAR
    # Retorna DEFAULT se o valor salvo for um estilo DiceBear antigo
    return style if style in AVATARES else DEFAULT_AVATAR


def sidebar_login():
    """Exibe login/cadastro e avatar na sidebar. Retorna username ou None."""
    with st.sidebar:
        st.markdown("---")
        st.subheader("Usuário")

        if st.session_state.get("usuario"):
            usuario = st.session_state["usuario"]
            avatar  = get_avatar(usuario)

            st.markdown(
                f"<div style='font-size:64px;text-align:center'>{avatar}</div>",
                unsafe_allow_html=True,
            )
            st.success(f"Olá, **{usuario}**!")

            saldo, em_jogo = _info_moedas(usuario)
            col1, col2 = st.columns(2)
            col1.metric("🪙 Saldo",  saldo)
            col2.metric("Em jogo", em_jogo)

            if st.button("Sair", use_container_width=True):
                del st.session_state["usuario"]
                st.rerun()
            return usuario

        nome = st.text_input("Seu nome", placeholder="Digite seu nome")
        if st.button("Entrar / Cadastrar", use_container_width=True):
            nome = nome.strip()
            if not nome:
                st.warning("Digite um nome")
            else:
                conn = get_connection()
                try:
                    conn.execute("INSERT OR IGNORE INTO usuarios (nome) VALUES (?)", (nome,))
                    conn.commit()
                    st.session_state["usuario"] = nome
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
                finally:
                    conn.close()

        return None
