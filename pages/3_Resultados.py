import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from api import get_resultados, get_resultados_espn
from database import get_connection, init_db
from scoring import calcular_pontos, calcular_ec_ganhos, is_surrealidade, DESCRICAO_PONTOS, fmt_ec
from utils import sidebar_login, apply_mobile_css

st.set_page_config(page_title="Resultados", page_icon="📋", layout="wide")

init_db()
apply_mobile_css()

API_KEY = st.secrets["API_KEY"]

with st.sidebar:
    st.title("⚽ Copa Elevação Sabichão")
    st.caption("Sistema de palpites para amigos")

usuario_logado = sidebar_login()

st.title("📋 Resultados & Admin")

tab_resultados, tab_processar, tab_admin = st.tabs([
    "Resultados Recentes", "Processar Pontos", "Admin"
])

# ── Resultados recentes ──────────────────────────────────────────────────────
with tab_resultados:
    @st.cache_data(ttl=900)
    def _resultados_api(key):
        return get_resultados(key, days_back=7)

    @st.cache_data(ttl=900)
    def _resultados_espn():
        return get_resultados_espn(days_back=14)

    jogos, erros = _resultados_api(API_KEY)
    jogos += _resultados_espn()

    if erros:
        with st.expander("Avisos"):
            for e in erros:
                st.warning(e)

    if not jogos:
        st.info("Nenhum resultado disponível nos últimos 7 dias.")
    else:
        # Agrupa por liga
        ligas_res = {}
        for j in jogos:
            if j.get("gols_casa") is not None and j.get("gols_fora") is not None:
                ligas_res.setdefault(j["liga"], []).append(j)

        for liga, jogos_liga in ligas_res.items():
            st.subheader(liga)
            for j in sorted(jogos_liga, key=lambda x: x["data"], reverse=True):
                try:
                    dt = datetime.fromisoformat(j["data"].replace("Z", "+00:00"))
                    data_fmt = dt.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M") + " BRT"
                except Exception:
                    data_fmt = j["data"]

                gc, gf = j["gols_casa"], j["gols_fora"]
                col_data, col_lc, col_jogo, col_lf = st.columns([1, 0.3, 5, 0.3])
                col_data.caption(data_fmt)
                if j.get("logo_casa"):
                    col_lc.image(j["logo_casa"], width=24)
                if j.get("logo_fora"):
                    col_lf.image(j["logo_fora"], width=24)
                if gc > gf:
                    col_jogo.markdown(f"**{j['casa']}** {gc} x {gf} {j['fora']}")
                elif gf > gc:
                    col_jogo.markdown(f"{j['casa']} {gc} x {gf} **{j['fora']}**")
                else:
                    col_jogo.markdown(f"{j['casa']} **{gc} x {gf}** {j['fora']}")
            st.divider()

# ── Processar pontos ─────────────────────────────────────────────────────────
with tab_processar:
    st.info("O processamento de resultados é feito automaticamente pelo bot a cada 5 minutos.")


# ── Admin ─────────────────────────────────────────────────────────────────────
with tab_admin:
    st.subheader("⚠️ Zona de perigo")
    ADMIN_PWD = st.secrets.get("ADMIN_PASSWORD", "")

    with st.expander("Migrar dados do SQLite local para Supabase"):
        st.caption("Execute uma única vez para transferir dados da instância local antes do redeploy.")
        if st.button("Executar migração SQLite → Supabase", key="btn_migrar"):
            import sqlite3 as _sqlite3
            import os as _os

            old_db = _os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "..", "data", "palpites.db"
            )
            if not _os.path.exists(old_db):
                st.warning("Arquivo SQLite local não encontrado. Nada a migrar.")
            else:
                try:
                    old = _sqlite3.connect(old_db)
                    old.row_factory = _sqlite3.Row
                    usuarios_old = old.execute("SELECT * FROM usuarios").fetchall()
                    palpites_old = old.execute("SELECT * FROM palpites").fetchall()
                    old.close()

                    new = get_connection()
                    u_ok = p_ok = 0

                    for u in usuarios_old:
                        try:
                            new.execute(
                                """INSERT INTO usuarios (nome, saldo_ec, avatar_style, senha_hash)
                                   VALUES (?, ?, ?, ?)
                                   ON CONFLICT (nome) DO NOTHING""",
                                (u["nome"], u["saldo_ec"] or 10.0,
                                 u["avatar_style"] or "⚽", u["senha_hash"]),
                            )
                            u_ok += 1
                        except Exception:
                            pass

                    for p in palpites_old:
                        try:
                            new.execute(
                                """INSERT INTO palpites
                                   (usuario, jogo_id, jogo, liga,
                                    palpite_casa, palpite_fora,
                                    gols_casa_real, gols_fora_real, pontos,
                                    moeda_apostada, moedas_ganhas,
                                    odds_casa, odds_empate, odds_fora, odd_apostada)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                   ON CONFLICT (usuario, jogo_id) DO NOTHING""",
                                (p["usuario"], p["jogo_id"], p["jogo"], p["liga"],
                                 p["palpite_casa"], p["palpite_fora"],
                                 p["gols_casa_real"], p["gols_fora_real"], p["pontos"],
                                 p["moeda_apostada"] or 0, p["moedas_ganhas"],
                                 p.get("odds_casa"), p.get("odds_empate"),
                                 p.get("odds_fora"), p.get("odd_apostada")),
                            )
                            p_ok += 1
                        except Exception:
                            pass

                    new.commit()
                    new.close()
                    st.success(f"Migração concluída! {u_ok} usuário(s) e {p_ok} palpite(s) transferidos.")
                except Exception as e:
                    st.error(f"Erro na migração: {e}")

    with st.expander("Resetar senha de usuário"):
        pwd_reset = st.text_input("Senha admin", type="password", key="admin_pwd_reset")
        col_u, col_s = st.columns(2)
        usuario_reset = col_u.text_input("Nome do usuário", key="usuario_reset")
        nova_senha    = col_s.text_input("Nova senha", type="password", key="nova_senha_reset")
        if st.button("Redefinir senha", key="btn_reset_senha"):
            if not ADMIN_PWD or pwd_reset != ADMIN_PWD:
                st.error("Senha admin incorreta.")
            elif not usuario_reset or not nova_senha:
                st.warning("Preencha o nome do usuário e a nova senha.")
            elif len(nova_senha) < 4:
                st.warning("A nova senha deve ter ao menos 4 caracteres.")
            else:
                import hashlib as _hashlib
                novo_hash = _hashlib.sha256(nova_senha.encode()).hexdigest()
                conn = get_connection()
                row = conn.execute(
                    "SELECT id FROM usuarios WHERE nome = ?", (usuario_reset,)
                ).fetchone()
                if not row:
                    st.error(f"Usuário '{usuario_reset}' não encontrado.")
                else:
                    conn.execute(
                        "UPDATE usuarios SET senha_hash = ? WHERE nome = ?",
                        (novo_hash, usuario_reset),
                    )
                    conn.commit()
                    st.success(f"Senha de **{usuario_reset}** redefinida com sucesso.")
                conn.close()

    with st.expander("Corrigir Resultado de Jogo"):
        st.caption("Use quando a API retornou um placar incorreto e os pontos já foram processados.")
        pwd_corr = st.text_input("Senha admin", type="password", key="admin_pwd_corr")

        conn_corr = get_connection()
        jogos_fin = conn_corr.execute(
            """SELECT id, jogo, liga, gols_casa, gols_fora
               FROM jogos WHERE status='FINISHED' AND gols_casa IS NOT NULL
               ORDER BY id DESC LIMIT 50"""
        ).fetchall()
        conn_corr.close()

        if not jogos_fin:
            st.info("Nenhum jogo finalizado encontrado no banco.")
        else:
            opcoes = {
                f"{j['jogo']} ({j['liga']}) — resultado atual: {j['gols_casa']}x{j['gols_fora']}": j["id"]
                for j in jogos_fin
            }
            jogo_selecionado = st.selectbox("Jogo a corrigir", list(opcoes.keys()), key="sel_jogo_corr")
            jogo_id_corr = opcoes[jogo_selecionado]

            col_gc_corr, col_gf_corr = st.columns(2)
            novo_gc = col_gc_corr.number_input("Gols Casa (correto)", min_value=0, max_value=20, step=1, key="novo_gc")
            novo_gf = col_gf_corr.number_input("Gols Fora (correto)", min_value=0, max_value=20, step=1, key="novo_gf")

            if st.button("Corrigir e Reprocessar", type="primary", key="btn_corrigir"):
                if not ADMIN_PWD or pwd_corr != ADMIN_PWD:
                    st.error("Senha admin incorreta.")
                else:
                    conn2 = get_connection()
                    # Busca todos os palpites JÁ processados para esse jogo
                    palpites_proc = conn2.execute(
                        """SELECT id, usuario, palpite_casa, palpite_fora,
                                  COALESCE(moeda_apostada, 0) as moeda_apostada,
                                  odd_apostada, moedas_ganhas
                           FROM palpites WHERE jogo_id=? AND pontos IS NOT NULL""",
                        (jogo_id_corr,),
                    ).fetchall()

                    corrigidos = 0
                    for p in palpites_proc:
                        old_ec = float(p["moedas_ganhas"]) if p["moedas_ganhas"] is not None else 0.0
                        moeda  = float(p["moeda_apostada"])

                        # Desfaz EC do processamento anterior
                        if old_ec >= 0:
                            # Usuário tinha ganho (ou empatou com odd 1.0): retira moeda_apostada + lucro que foi creditado
                            conn2.execute(
                                "UPDATE usuarios SET saldo_ec = saldo_ec - ? WHERE nome=?",
                                (moeda + old_ec, p["usuario"]),
                            )
                        # (se old_ec < 0, a aposta já foi descontada na hora do palpite — nada a desfazer)

                        # Recalcula com placar correto
                        pts    = calcular_pontos(p["palpite_casa"], p["palpite_fora"], novo_gc, novo_gf)
                        surreal = is_surrealidade(p["palpite_casa"], p["palpite_fora"])
                        new_ec = calcular_ec_ganhos(pts, moeda, p["odd_apostada"],
                                                    surrealidade=(surreal and pts is not None and pts > 0))

                        conn2.execute(
                            """UPDATE palpites
                               SET gols_casa_real=?, gols_fora_real=?, pontos=?, moedas_ganhas=?
                               WHERE id=?""",
                            (novo_gc, novo_gf, pts, new_ec, p["id"]),
                        )

                        # Aplica novo EC se ganhou (>0) ou devolveu stake com odd 1.0 (==0)
                        if new_ec >= 0:
                            conn2.execute(
                                "UPDATE usuarios SET saldo_ec = saldo_ec + ? WHERE nome=?",
                                (moeda + new_ec, p["usuario"]),
                            )
                        corrigidos += 1

                    # Corrige placar na tabela jogos
                    conn2.execute(
                        "UPDATE jogos SET gols_casa=?, gols_fora=? WHERE id=?",
                        (novo_gc, novo_gf, jogo_id_corr),
                    )
                    conn2.commit()
                    conn2.close()
                    st.success(f"Resultado corrigido para **{novo_gc}x{novo_gf}** · {corrigidos} palpite(s) reprocessado(s).")

    with st.expander("Resetar banco de dados"):
        pwd_input = st.text_input("Senha admin", type="password", key="reset_pwd")
        if st.button("Apagar todos usuários e palpites", type="primary"):
            if not ADMIN_PWD or pwd_input != ADMIN_PWD:
                st.error("Senha incorreta.")
            else:
                conn = get_connection()
                conn.execute("DELETE FROM palpites")
                conn.execute("DELETE FROM usuarios")
                conn.commit()
                conn.close()
                st.success("Banco resetado. Todos os usuários e palpites foram apagados.")
                st.rerun()
