import hashlib
import streamlit as st
from database import get_connection

AVATARES = [
    "⚽", "🏆", "👑", "🔥", "⚡", "🎯", "💎", "🌟",
    "🦁", "🐯", "🦊", "🐺", "🦅", "🦈", "🐊", "🦝",
    "🤠", "😎", "🥷", "🤖", "👾", "🎭", "🧙", "🏴‍☠️",
]

DEFAULT_AVATAR = "⚽"


def _hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


def _info_ec(usuario):
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(saldo_ec, saldo_moedas, 10) as saldo FROM usuarios WHERE nome=?",
        (usuario,),
    ).fetchone()
    em_jogo = conn.execute(
        "SELECT COALESCE(SUM(moeda_apostada), 0) as c FROM palpites WHERE usuario=? AND moeda_apostada > 0 AND pontos IS NULL",
        (usuario,),
    ).fetchone()["c"]
    conn.close()
    return float(row["saldo"] if row else 10.0), float(em_jogo)


def get_avatar(usuario):
    conn = get_connection()
    row  = conn.execute("SELECT avatar_style FROM usuarios WHERE nome=?", (usuario,)).fetchone()
    conn.close()
    style = row["avatar_style"] if row and row["avatar_style"] else DEFAULT_AVATAR
    return style if style in AVATARES else DEFAULT_AVATAR


def sidebar_login():
    """Exibe login/cadastro com senha e avatar na sidebar. Retorna username ou None."""
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

            saldo, em_jogo = _info_ec(usuario)
            col1, col2 = st.columns(2)
            col1.metric("💰 Disponível", f"{max(saldo - em_jogo, 0):.2f}")
            col2.metric("Em jogo", f"{em_jogo:.2f}")

            if st.button("Sair", use_container_width=True):
                del st.session_state["usuario"]
                st.rerun()
            return usuario

        # Formulário de login / cadastro
        nome  = st.text_input("Nome", placeholder="Seu nome de usuário")
        senha = st.text_input("Senha", type="password", placeholder="Sua senha")

        col_login, col_cadastro = st.columns(2)

        # ── Entrar ────────────────────────────────────────────────────────────
        if col_login.button("Entrar", use_container_width=True, type="primary"):
            nome = nome.strip()
            if not nome or not senha:
                st.warning("Preencha nome e senha.")
            else:
                conn = get_connection()
                row  = conn.execute(
                    "SELECT nome, senha_hash FROM usuarios WHERE nome=?", (nome,)
                ).fetchone()
                conn.close()

                if row is None:
                    st.error("Usuário não encontrado.")
                elif row["senha_hash"] is None:
                    # Conta sem senha (migração) — define a senha agora
                    conn = get_connection()
                    conn.execute(
                        "UPDATE usuarios SET senha_hash=? WHERE nome=?",
                        (_hash(senha), nome),
                    )
                    conn.commit()
                    conn.close()
                    st.session_state["usuario"] = nome
                    st.rerun()
                elif row["senha_hash"] != _hash(senha):
                    st.error("Senha incorreta.")
                else:
                    st.session_state["usuario"] = nome
                    st.rerun()

        # ── Cadastrar ─────────────────────────────────────────────────────────
        if col_cadastro.button("Cadastrar", use_container_width=True):
            nome = nome.strip()
            if not nome or not senha:
                st.warning("Preencha nome e senha.")
            elif len(senha) < 4:
                st.warning("Senha deve ter ao menos 4 caracteres.")
            else:
                conn = get_connection()
                existe = conn.execute(
                    "SELECT id FROM usuarios WHERE nome=?", (nome,)
                ).fetchone()
                if existe:
                    st.error("Nome já cadastrado. Escolha outro ou faça login.")
                    conn.close()
                else:
                    try:
                        conn.execute(
                            "INSERT INTO usuarios (nome, senha_hash) VALUES (?, ?)",
                            (nome, _hash(senha)),
                        )
                        conn.commit()
                        st.session_state["usuario"] = nome
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")
                    finally:
                        conn.close()

        return None
