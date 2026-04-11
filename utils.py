import streamlit as st
from database import get_connection


def sidebar_login():
    """
    Exibe login/cadastro na sidebar.
    Retorna o nome do usuário logado ou None.
    """
    with st.sidebar:
        st.markdown("---")
        st.subheader("Usuário")

        if st.session_state.get("usuario"):
            st.success(f"Olá, **{st.session_state.usuario}**!")
            if st.button("Sair", use_container_width=True):
                del st.session_state["usuario"]
                st.rerun()
            return st.session_state["usuario"]

        nome = st.text_input("Seu nome", placeholder="Digite seu nome")

        if st.button("Entrar / Cadastrar", use_container_width=True):
            nome = nome.strip()
            if not nome:
                st.warning("Digite um nome")
            else:
                conn = get_connection()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO usuarios (nome) VALUES (?)", (nome,)
                    )
                    conn.commit()
                    st.session_state["usuario"] = nome
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
                finally:
                    conn.close()

        return None
