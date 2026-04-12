import streamlit as st
import pandas as pd
from datetime import datetime
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

    # Resultados manuais finalizados
    conn = get_connection()
    manuais_fin = conn.execute(
        "SELECT id, liga, data, casa, fora, gols_casa, gols_fora FROM jogos_manuais WHERE status = 'FINISHED' ORDER BY data DESC"
    ).fetchall()
    conn.close()

    for r in manuais_fin:
        jogos.append({
            "id": f"manual_{r['id']}",
            "liga": r["liga"],
            "data": r["data"],
            "casa": r["casa"],
            "fora": r["fora"],
            "gols_casa": r["gols_casa"],
            "gols_fora": r["gols_fora"],
            "label": f"[{r['liga']}] {r['casa']} {r['gols_casa']}x{r['gols_fora']} {r['fora']}",
            "fonte": "manual",
        })

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
                    data_fmt = dt.strftime("%d/%m %H:%M")
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
    st.markdown("""
    Clique em **Processar** para buscar resultados recentes e calcular os pontos
    dos palpites que ainda não foram avaliados.
    """)

    if st.button("Processar resultados da API", type="primary"):
        with st.spinner("Buscando resultados..."):
            jogos_fin, erros = get_resultados(API_KEY, days_back=14)
            jogos_fin += get_resultados_espn(days_back=14)

        if erros:
            for e in erros:
                st.warning(e)

        if not jogos_fin:
            st.info("Nenhum resultado encontrado.")
        else:
            conn = get_connection()
            atualizados = 0

            for j in jogos_fin:
                gc, gf = j["gols_casa"], j["gols_fora"]
                if gc is None or gf is None:
                    continue

                palpites = conn.execute(
                    """SELECT id, usuario, palpite_casa, palpite_fora,
                              COALESCE(moeda_apostada, 0) as moeda_apostada, odd_apostada
                       FROM palpites WHERE jogo_id=? AND pontos IS NULL""",
                    (j["id"],),
                ).fetchall()

                for p in palpites:
                    pts    = calcular_pontos(p["palpite_casa"], p["palpite_fora"], gc, gf)
                    surreal = is_surrealidade(p["palpite_casa"], p["palpite_fora"])
                    ec     = calcular_ec_ganhos(pts, p["moeda_apostada"], p["odd_apostada"],
                                               surrealidade=(surreal and pts is not None and pts > 0))
                    conn.execute(
                        "UPDATE palpites SET gols_casa_real=?, gols_fora_real=?, pontos=?, moedas_ganhas=? WHERE id=?",
                        (gc, gf, pts, ec, p["id"]),
                    )
                    if ec != 0:
                        conn.execute(
                            "UPDATE usuarios SET saldo_ec = saldo_ec + ? WHERE nome=?",
                            (ec, p["usuario"]),
                        )
                    atualizados += 1

            conn.commit()
            conn.close()
            st.success(f"{atualizados} palpite(s) avaliado(s)!")

    st.divider()
    st.subheader("Processar jogos manuais")
    st.caption("Informe o resultado de um jogo manual para calcular os palpites.")

    conn = get_connection()
    manuais_pend = conn.execute(
        "SELECT id, liga, casa, fora FROM jogos_manuais WHERE status = 'SCHEDULED'"
    ).fetchall()
    conn.close()

    if not manuais_pend:
        st.info("Nenhum jogo manual pendente de resultado.")
    else:
        opcoes = {f"[{r['liga']}] {r['casa']} x {r['fora']}": r["id"] for r in manuais_pend}
        jogo_sel = st.selectbox("Jogo manual", list(opcoes.keys()))
        jogo_id = opcoes[jogo_sel]

        col1, col2 = st.columns(2)
        gc_m = col1.number_input("Gols casa", min_value=0, max_value=20, key="gc_manual")
        gf_m = col2.number_input("Gols fora", min_value=0, max_value=20, key="gf_manual")

        if st.button("Salvar resultado e calcular pontos"):
            conn = get_connection()
            conn.execute(
                "UPDATE jogos_manuais SET gols_casa=?, gols_fora=?, status='FINISHED' WHERE id=?",
                (gc_m, gf_m, jogo_id),
            )

            jid_str = f"manual_{jogo_id}"
            palpites = conn.execute(
                """SELECT id, usuario, palpite_casa, palpite_fora,
                          COALESCE(moeda_apostada, 0) as moeda_apostada, odd_apostada
                   FROM palpites WHERE jogo_id=? AND pontos IS NULL""",
                (jid_str,),
            ).fetchall()

            atualizados = 0
            for p in palpites:
                pts     = calcular_pontos(p["palpite_casa"], p["palpite_fora"], gc_m, gf_m)
                surreal = is_surrealidade(p["palpite_casa"], p["palpite_fora"])
                ec      = calcular_ec_ganhos(pts, p["moeda_apostada"], p["odd_apostada"],
                                             surrealidade=(surreal and pts is not None and pts > 0))
                conn.execute(
                    "UPDATE palpites SET gols_casa_real=?, gols_fora_real=?, pontos=?, moedas_ganhas=? WHERE id=?",
                    (gc_m, gf_m, pts, ec, p["id"]),
                )
                if ec != 0:
                    conn.execute(
                        "UPDATE usuarios SET saldo_ec = saldo_ec + ? WHERE nome=?",
                        (ec, p["usuario"]),
                    )
                atualizados += 1

            conn.commit()
            conn.close()
            st.success(f"Resultado salvo! {atualizados} palpite(s) avaliado(s).")
            st.rerun()

# ── Admin ─────────────────────────────────────────────────────────────────────
with tab_admin:
    st.subheader("⚠️ Zona de perigo")
    ADMIN_PWD = st.secrets.get("ADMIN_PASSWORD", "")
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
