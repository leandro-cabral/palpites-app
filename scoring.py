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


def calcular_moedas_ganhas(pontos, moeda_apostada, odd_apostada=None):
    """
    Retorna o delta de moedas ao processar um resultado.
      Acertou → max(1, round(pontos × odd))
      Errou   → -1
      Sem moeda → 0
    """
    if not moeda_apostada:
        return 0
    if pontos == 0:
        return -1
    odd = odd_apostada or 1.0
    return max(1, round(pontos * odd))
