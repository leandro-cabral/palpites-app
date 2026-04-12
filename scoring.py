def calcular_pontos(palpite_casa, palpite_fora, real_casa, real_fora):
    """
    Sistema de pontuação:
      3 pts — placar exato
      2 pts — empate acertado (placar diferente)
      1 pt  — vencedor correto (placar diferente)
      0 pts — erro
    """
    if real_casa is None or real_fora is None:
        return None

    if palpite_casa == real_casa and palpite_fora == real_fora:
        return 3

    def resultado(c, f):
        if c > f:
            return "V"
        if c < f:
            return "D"
        return "E"

    res_palpite = resultado(palpite_casa, palpite_fora)
    res_real = resultado(real_casa, real_fora)

    if res_palpite == res_real:
        return 2 if res_real == "E" else 1

    return 0


DESCRICAO_PONTOS = {
    3: "Placar exato",
    2: "Empate acertado",
    1: "Vencedor certo",
    0: "Errou",
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


def calcular_ec_ganhos(pontos, valor_apostado, odd_apostada=None):
    """
    Retorna o delta de Elevação Coins ao processar um resultado.
      Acertou resultado  → valor × odd − valor  (lucro líquido)
      Acertou placar exato → valor × odd × 1.5 − valor  (bônus 50%)
      Errou              → −valor_apostado
      Sem aposta         → 0.0
    """
    if not valor_apostado:
        return 0.0
    if pontos == 0:
        return -float(valor_apostado)
    odd   = float(odd_apostada or 1.0)
    bonus = 1.5 if pontos == 3 else 1.0
    return valor_apostado * odd * bonus - valor_apostado
