def is_surrealidade(casa, fora):
    """
    Um placar é 'surrealidade' se a diferença de gols >= 3 OU o total de gols > 4.
    Ex: 3-0, 4-1, 5-2, 3-3, 5-1, 0-3, ...
    """
    return abs(casa - fora) >= 3 or (casa + fora) >= 4


def calcular_pontos(palpite_casa, palpite_fora, real_casa, real_fora):
    """
    Sistema de pontuação base:
      4.5 pts — placar exato
      3.0 pts — empate acertado (placar diferente)
      1.5 pts — vencedor correto (placar diferente)
      -1  pt  — resultado errado

    Bônus Surrealidade (palpite com diferença >= 3 ou total > 4):
      Acerto → pontos × 2  (9.0 / 6.0 / 3.0)
      Erro   → -2 pts
    """
    if real_casa is None or real_fora is None:
        return None

    surreal = is_surrealidade(palpite_casa, palpite_fora)

    if palpite_casa == real_casa and palpite_fora == real_fora:
        return 9.0 if surreal else 4.5

    def resultado(c, f):
        if c > f:
            return "V"
        if c < f:
            return "D"
        return "E"

    res_palpite = resultado(palpite_casa, palpite_fora)
    res_real = resultado(real_casa, real_fora)

    if res_palpite == res_real:
        base = 3.0 if res_real == "E" else 1.5
        return base * 2 if surreal else base

    return -2.0 if surreal else -1.0


DESCRICAO_PONTOS = {
    9.0:  "Placar exato (Surrealidade!)",
    6.0:  "Empate acertado (Surrealidade!)",
    4.5:  "Placar exato",
    3.0:  "Vencedor/Empate certo (Surrealidade!)",
    1.5:  "Vencedor certo",
    -1.0: "Errou",
    -2.0: "Errou (Surrealidade!)",
}


def fmt_ec(valor):
    """Formata valor de Elevação Coin para exibição."""
    if valor is None:
        return "—"
    return f"{valor:+.2f} EC" if valor != 0 else "0 EC"


def calcular_score_ranking(total_pontos, saldo_ec, ec_em_jogo):
    """
    Score do ranking = Pontos × Banca disponível.
    Banca disponível = saldo_ec − ec_em_jogo (nunca negativa).
    """
    banca = max(float(saldo_ec) - float(ec_em_jogo), 0)
    return round(total_pontos * banca, 2)


def ordenar_ranking(jogadores):
    """
    Ordena lista de dicts de jogadores pelo critério do ranking:
      1. Score (pontos × banca) — maior primeiro
      2. Desempate: total_pontos — maior primeiro
      3. Desempate: placares_exatos — maior primeiro
    Cada dict deve ter: score, total_pontos, placares_exatos.
    Retorna nova lista ordenada.
    """
    return sorted(
        jogadores,
        key=lambda x: (x["score"], x["total_pontos"], x["placares_exatos"]),
        reverse=True,
    )


def calcular_ec_ganhos(pontos, valor_apostado, odd_apostada=None, surrealidade=False):
    """
    Retorna o delta de Elevação Coins ao processar um resultado.
      Acertou resultado    → valor × odd − valor  (lucro líquido)
      Acertou placar exato → valor × odd × 1.5 − valor  (bônus 50%)
      Errou                → −valor_apostado
      Sem aposta           → 0.0
      Surrealidade acerto  → EC lucro × 2
      Surrealidade erro    → −valor_apostado (igual ao erro normal)
    """
    if not valor_apostado:
        return 0.0
    if pontos is None or pontos <= 0:
        return -float(valor_apostado)
    odd = float(odd_apostada or 1.0)
    # Normaliza pontos para detectar placar exato (9.0 é exato surrealidade)
    base_pts = pontos / 2 if surrealidade else pontos
    bonus = 1.5 if base_pts == 4.5 else 1.0
    ec = valor_apostado * odd * bonus - valor_apostado
    return ec * 2 if surrealidade else ec
