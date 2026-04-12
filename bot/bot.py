import os
import discord
from discord.ext import tasks
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta

DISCORD_TOKEN  = os.environ["DISCORD_TOKEN"]
CHANNEL_ID     = int(os.environ["DISCORD_CHANNEL_ID"])
DATABASE_URL   = os.environ["DATABASE_URL"]

intents = discord.Intents.default()
client  = discord.Client(intents=intents)


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ── Eventos ───────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")
    checar_lembretes.start()
    checar_resultados.start()


# ── Task 1: Lembrete 2h antes do jogo ────────────────────────────────────────

@tasks.loop(minutes=1)
async def checar_lembretes():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    agora = datetime.now(timezone.utc)
    em_2h = agora + timedelta(hours=2)
    em_3h = agora + timedelta(hours=3)

    try:
        conn = get_conn()
        c    = cur(conn)

        c.execute("""
            SELECT id, liga, casa, fora, data
            FROM jogos
            WHERE status = 'SCHEDULED'
              AND lembrete_enviado = FALSE
              AND data > %s
              AND data <= %s
        """, (em_2h, em_3h))
        jogos = c.fetchall()

        for jogo in jogos:
            c.execute("""
                SELECT nome FROM usuarios
                WHERE nome NOT IN (
                    SELECT usuario FROM palpites WHERE jogo_id = %s
                )
            """, (jogo["id"],))
            sem_palpite = [r["nome"] for r in c.fetchall()]

            horario = jogo["data"].astimezone(timezone(timedelta(hours=-3))).strftime("%H:%M")

            embed = discord.Embed(
                title=f"⏰ {jogo['casa']} x {jogo['fora']}",
                description=f"**{jogo['liga']}** — começa às {horario} (BRT)\nFaltam ~2 horas!",
                color=0xff4500,
            )

            if sem_palpite:
                embed.add_field(
                    name="Ainda não apostaram",
                    value=", ".join(f"**{n}**" for n in sem_palpite),
                    inline=False,
                )
            else:
                embed.add_field(name="✅ Todos apostaram!", value="Boa sorte a todos.", inline=False)

            await channel.send(embed=embed)

            c.execute("UPDATE jogos SET lembrete_enviado = TRUE WHERE id = %s", (jogo["id"],))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[lembretes] Erro: {e}")


# ── Task 2: Resultados e ranking ──────────────────────────────────────────────

@tasks.loop(minutes=5)
async def checar_resultados():
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        return

    try:
        conn = get_conn()
        c    = cur(conn)

        c.execute("""
            SELECT id, liga, casa, fora, gols_casa, gols_fora
            FROM jogos
            WHERE status = 'FINISHED'
              AND resultado_notificado = FALSE
              AND data > NOW() - INTERVAL '48 hours'
        """)
        jogos = c.fetchall()

        if not jogos:
            conn.close()
            return

        for jogo in jogos:
            c.execute("""
                SELECT usuario, palpite_casa, palpite_fora, pontos,
                       moeda_apostada, moedas_ganhas
                FROM palpites
                WHERE jogo_id = %s AND pontos IS NOT NULL
                ORDER BY pontos DESC
            """, (jogo["id"],))
            palpites = c.fetchall()

            embed = discord.Embed(
                title=f"⚽ {jogo['casa']} {jogo['gols_casa']} x {jogo['gols_fora']} {jogo['fora']}",
                color=0x00d2ff,
            )
            embed.set_footer(text=jogo["liga"])

            if palpites:
                linhas = []
                for p in palpites:
                    pts = p["pontos"]
                    ec  = p["moedas_ganhas"]
                    if pts > 0:
                        pts_emoji = "🟢"
                    elif pts == 0:
                        pts_emoji = "🟡"
                    else:
                        pts_emoji = "🔴"
                    ec_str = f"`{ec:+.2f} EC`" if ec is not None else "—"
                    linhas.append(
                        f"{pts_emoji} **{p['usuario']}** — "
                        f"`{p['palpite_casa']}x{p['palpite_fora']}` · "
                        f"**{pts} pts** · {ec_str}"
                    )
                embed.description = "\n".join(linhas)
            else:
                embed.description = "_Nenhum palpite registrado para este jogo._"

            await channel.send(embed=embed)
            c.execute("UPDATE jogos SET resultado_notificado = TRUE WHERE id = %s", (jogo["id"],))

        # Ranking após processar todos os jogos
        c.execute("""
            SELECT p.usuario,
                   COALESCE(SUM(p.pontos), 0)   AS total_pontos,
                   u.saldo_ec
            FROM palpites p
            JOIN usuarios u ON p.usuario = u.nome
            WHERE p.moeda_apostada > 0
            GROUP BY p.usuario, u.saldo_ec
            ORDER BY (COALESCE(SUM(p.pontos), 0) * u.saldo_ec) DESC,
                     COALESCE(SUM(p.pontos), 0) DESC
        """)
        ranking = c.fetchall()

        if ranking:
            medals = ["🥇", "🥈", "🥉"]
            linhas = []
            for i, r in enumerate(ranking):
                medal  = medals[i] if i < 3 else f"**{i+1}.**"
                score  = round(r["total_pontos"] * r["saldo_ec"], 2)
                linhas.append(
                    f"{medal} **{r['usuario']}** — "
                    f"{r['total_pontos']} pts · "
                    f"💰 {r['saldo_ec']:.2f} EC · "
                    f"⭐ {score}"
                )

            rank_embed = discord.Embed(
                title="🏆 Ranking Lisan al Gaib — Atualizado",
                description="\n".join(linhas),
                color=0xeab308,
            )
            await channel.send(embed=rank_embed)

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[resultados] Erro: {e}")


client.run(DISCORD_TOKEN)
