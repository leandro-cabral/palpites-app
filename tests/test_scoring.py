"""
Testes das regras de negócio: pontuação e cálculo de EC (Elevação Coin).

Regras:
  Pontuação base
    4.5 pts — placar exato
    3.0 pts — empate acertado (placar diferente)
    1.5 pts — vencedor correto (placar diferente)
    -1  pt  — erro
    None    — jogo sem resultado real

  Bônus Surrealidade (palpite com dif >= 3 gols ou total > 4 gols)
    Acerto → pontos × 2  (9.0 / 6.0 / 3.0)
    Erro   → -2 pts

  EC (calcular_ec_ganhos)
    Sem aposta              → 0.0
    Erro                    → -valor_apostado
    Acerto (1.5 ou 3.0 pts) → valor × odd − valor   (lucro líquido)
    Placar exato (4.5 pts)  → valor × odd × 1.5 − valor  (bônus 50%)
    Surrealidade acerto     → EC lucro × 2
    Surrealidade erro       → -valor_apostado (igual ao erro normal)
"""

import pytest
from scoring import calcular_pontos, calcular_ec_ganhos, is_surrealidade, fmt_ec


# ── calcular_pontos ───────────────────────────────────────────────────────────

class TestCalcularPontos:

    # Placar exato
    def test_placar_exato_vitoria_casa(self):
        assert calcular_pontos(2, 1, 2, 1) == 4.5

    def test_placar_exato_vitoria_fora(self):
        # 0-3 tem diferença 3 → surrealidade → 9.0
        assert calcular_pontos(0, 3, 0, 3) == 9.0

    def test_placar_exato_empate(self):
        assert calcular_pontos(1, 1, 1, 1) == 4.5

    def test_placar_exato_0x0(self):
        assert calcular_pontos(0, 0, 0, 0) == 4.5

    # Empate acertado (placar diferente)
    def test_empate_acertado_placar_diferente(self):
        # 2-2 total=4 >= 4 → surrealidade → 3.0 × 2 = 6.0
        assert calcular_pontos(2, 2, 1, 1) == 6.0

    def test_empate_acertado_outro_placar(self):
        assert calcular_pontos(0, 0, 3, 3) == 3.0

    # Vencedor correto (placar diferente)
    def test_vencedor_casa_correto(self):
        assert calcular_pontos(2, 0, 3, 1) == 1.5

    def test_vencedor_fora_correto(self):
        assert calcular_pontos(0, 1, 0, 4) == 1.5

    def test_vencedor_casa_placar_bem_diferente(self):
        assert calcular_pontos(1, 0, 5, 0) == 1.5

    # Erro
    def test_errou_resultado_oposto(self):
        assert calcular_pontos(2, 1, 0, 1) == -1.0

    def test_errou_empate_esperado_vitoria_real(self):
        assert calcular_pontos(1, 1, 2, 0) == -1.0

    def test_errou_vitoria_esperada_empate_real(self):
        # 3-1 total=4 >= 4 → surrealidade → erro = -2.0
        assert calcular_pontos(3, 1, 2, 2) == -2.0

    # Sem resultado real
    def test_sem_resultado_retorna_none(self):
        assert calcular_pontos(1, 0, None, None) is None

    def test_resultado_parcialmente_none(self):
        assert calcular_pontos(1, 0, 1, None) is None


class TestIsSurrealidade:

    def test_diferenca_3_e_surrealidade(self):
        assert is_surrealidade(3, 0) is True

    def test_diferenca_4_e_surrealidade(self):
        assert is_surrealidade(0, 4) is True

    def test_total_5_e_surrealidade(self):
        assert is_surrealidade(3, 2) is True  # total=5 > 4

    def test_empate_alto_e_surrealidade(self):
        assert is_surrealidade(3, 3) is True  # total=6 > 4

    def test_diferenca_2_total_4_e_surrealidade(self):
        assert is_surrealidade(3, 1) is True  # dif=2, total=4 >= 4

    def test_0x0_nao_e_surrealidade(self):
        assert is_surrealidade(0, 0) is False

    def test_1x1_nao_e_surrealidade(self):
        assert is_surrealidade(1, 1) is False

    def test_2x2_e_surrealidade(self):
        assert is_surrealidade(2, 2) is True  # total=4 >= 4

    def test_2x0_nao_e_surrealidade(self):
        assert is_surrealidade(2, 0) is False  # dif=2, total=2

    def test_1x3_nao_e_surrealidade_pela_diferenca_mas_sim_pelo_total(self):
        assert is_surrealidade(1, 3) is True  # total=4 >= 4


class TestCalcularPontosSurrealidade:

    # Surrealidade acerto — pontos × 2
    def test_placar_exato_surrealidade(self):
        assert calcular_pontos(3, 0, 3, 0) == 9.0

    def test_placar_exato_surrealidade_fora(self):
        assert calcular_pontos(0, 4, 0, 4) == 9.0

    def test_vencedor_correto_surrealidade(self):
        # palpitou 3-0, real foi 4-0 (diferença 4, surrealidade); acertou vencedor
        assert calcular_pontos(3, 0, 4, 0) == 3.0  # 1.5 × 2

    def test_empate_acertado_surrealidade(self):
        # palpitou 3-3, real foi 2-2 (total 6, surrealidade); acertou empate
        assert calcular_pontos(3, 3, 2, 2) == 6.0  # 3.0 × 2

    # Surrealidade erro — -2 pts
    def test_erro_surrealidade(self):
        # palpitou 3-0 (surrealidade), real foi 0-1 (errou)
        assert calcular_pontos(3, 0, 0, 1) == -2.0

    def test_erro_surrealidade_total_alto(self):
        # palpitou 3-2 (total 5, surrealidade), real foi empate
        assert calcular_pontos(3, 2, 1, 1) == -2.0

    # Placar normal não é afetado
    def test_placar_normal_nao_e_surrealidade(self):
        assert calcular_pontos(2, 1, 2, 1) == 4.5  # exato normal


# ── calcular_ec_ganhos ────────────────────────────────────────────────────────

class TestCalcularEcGanhos:

    # Sem aposta
    def test_sem_aposta_zero_retorna_zero(self):
        assert calcular_ec_ganhos(4.5, 0) == 0.0

    def test_sem_aposta_none_retorna_zero(self):
        assert calcular_ec_ganhos(1.5, None) == 0.0

    # Erro (-1 pt) — perde o apostado
    def test_erro_perde_aposta_inteira(self):
        assert calcular_ec_ganhos(-1.0, 5) == -5.0

    def test_erro_perde_aposta_decimal(self):
        assert calcular_ec_ganhos(-1.0, 3.5) == -3.5

    def test_erro_perde_com_odd_alta(self):
        # Odd não importa se errou — perde o valor apostado
        assert calcular_ec_ganhos(-1.0, 10, odd_apostada=5.0) == -10.0

    # Acerto simples (1.5 ou 3.0 pts): lucro = valor × odd − valor
    def test_acerto_vencedor_odd_2(self):
        # apostou 10 na vitória com odd 2.0 → lucro = 10*2 - 10 = 10
        resultado = calcular_ec_ganhos(1.5, 10, odd_apostada=2.0)
        assert abs(resultado - 10.0) < 0.001

    def test_acerto_empate_odd_3(self):
        # apostou 5 no empate com odd 3.0 → lucro = 5*3 - 5 = 10
        resultado = calcular_ec_ganhos(3.0, 5, odd_apostada=3.0)
        assert abs(resultado - 10.0) < 0.001

    def test_acerto_vencedor_odd_1_5(self):
        # apostou 4 com odd 1.5 → lucro = 4*1.5 - 4 = 2
        resultado = calcular_ec_ganhos(1.5, 4, odd_apostada=1.5)
        assert abs(resultado - 2.0) < 0.001

    def test_acerto_sem_odd_usa_odd_1(self):
        # Sem odd definida → usa 1.0 → lucro = valor*1 - valor = 0
        resultado = calcular_ec_ganhos(1.5, 5, odd_apostada=None)
        assert abs(resultado - 0.0) < 0.001

    # Placar exato (4.5 pts): bônus 50% → lucro = valor × odd × 1.5 − valor
    def test_exato_bonus_50pct_odd_2(self):
        # apostou 10 com odd 2.0 → lucro = 10*2*1.5 - 10 = 20
        resultado = calcular_ec_ganhos(4.5, 10, odd_apostada=2.0)
        assert abs(resultado - 20.0) < 0.001

    def test_exato_bonus_50pct_odd_3(self):
        # apostou 4 com odd 3.0 → lucro = 4*3*1.5 - 4 = 14
        resultado = calcular_ec_ganhos(4.5, 4, odd_apostada=3.0)
        assert abs(resultado - 14.0) < 0.001

    def test_exato_sem_odd_usa_odd_1(self):
        # odd=None → 1.0 → lucro = 10*1*1.5 - 10 = 5
        resultado = calcular_ec_ganhos(4.5, 10, odd_apostada=None)
        assert abs(resultado - 5.0) < 0.001

    # Coerência: exato sempre rende mais que acerto simples na mesma odd
    def test_exato_rende_mais_que_acerto_simples(self):
        aposta, odd = 10, 2.5
        ec_exato   = calcular_ec_ganhos(4.5, aposta, odd_apostada=odd)
        ec_simples = calcular_ec_ganhos(1.5, aposta, odd_apostada=odd)
        assert ec_exato > ec_simples

    # Valores decimais precisos (sem arredondamento)
    def test_sem_arredondamento(self):
        resultado = calcular_ec_ganhos(1.5, 7, odd_apostada=1.85)
        esperado  = 7 * 1.85 - 7  # = 5.95
        assert abs(resultado - esperado) < 0.0001

    # Surrealidade acerto — EC × 2
    def test_surrealidade_exato_dobra_ec(self):
        # normal exact: 10 * 2.0 * 1.5 - 10 = 20; surrealidade: 40
        normal = calcular_ec_ganhos(4.5, 10, odd_apostada=2.0)
        surreal = calcular_ec_ganhos(9.0, 10, odd_apostada=2.0, surrealidade=True)
        assert abs(surreal - normal * 2) < 0.001

    def test_surrealidade_vencedor_dobra_ec(self):
        # normal: 5 * 2.0 - 5 = 5; surrealidade: 10
        normal = calcular_ec_ganhos(1.5, 5, odd_apostada=2.0)
        surreal = calcular_ec_ganhos(3.0, 5, odd_apostada=2.0, surrealidade=True)
        assert abs(surreal - normal * 2) < 0.001

    # Surrealidade erro — EC = -valor (igual ao erro normal)
    def test_surrealidade_erro_perde_aposta_normal(self):
        assert calcular_ec_ganhos(-2.0, 10, odd_apostada=3.0) == -10.0


# ── Ciclo completo de saldo ───────────────────────────────────────────────────

class TestCicloSaldo:
    """
    Simula o ciclo: saldo inicial → aposta → resultado → novo saldo.
    Verifica que o saldo final bate com a expectativa.
    """

    def _novo_saldo(self, saldo, aposta, pontos, odd):
        ec = calcular_ec_ganhos(pontos, aposta, odd_apostada=odd)
        return saldo + ec

    def test_ciclo_ganhou_saldo_aumenta(self):
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=1.5, odd=2.0)
        assert saldo_final == 15.0  # lucro = 5*2 - 5 = 5

    def test_ciclo_perdeu_saldo_diminui(self):
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=-1.0, odd=2.0)
        assert saldo_final == 5.0  # perde 5

    def test_ciclo_exato_saldo_aumenta_mais(self):
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=4.5, odd=2.0)
        assert saldo_final == 20.0  # lucro = 5*2*1.5 - 5 = 10

    def test_ciclo_sem_aposta_saldo_inalterado(self):
        saldo_final = self._novo_saldo(10.0, aposta=0, pontos=4.5, odd=2.0)
        assert saldo_final == 10.0

    def test_ciclo_multiplos_jogos(self):
        """
        Jogo A: apostou 3 EC @ odd 2.0, acertou vencedor (1.5 pts)
          → lucro = 3*2 - 3 = 3
        Jogo B: apostou 2 EC @ odd 3.2, errou (-1 pt)
          → perde = -2
        Jogo C: apostou 4 EC @ odd 1.8, acertou placar exato (4.5 pts)
          → lucro = 4*1.8*1.5 - 4 = 6.8
        Saldo inicial: 10 → esperado: 10 + 3 - 2 + 6.8 = 17.8
        """
        saldo = 10.0
        saldo += calcular_ec_ganhos(1.5, 3, odd_apostada=2.0)
        saldo += calcular_ec_ganhos(-1.0, 2, odd_apostada=3.2)
        saldo += calcular_ec_ganhos(4.5, 4, odd_apostada=1.8)
        assert abs(saldo - 17.8) < 0.001

    def test_ciclo_surrealidade_acerto(self):
        """
        Palpitou 3-0 (surrealidade) com odd 2.0, apostou 5 EC, acertou (9.0 pts)
          lucro base = 5*2*1.5 - 5 = 10 (exato com bônus 50%)
          surrealidade × 2 → lucro = 20
        Saldo: 10 + 20 = 30
        """
        saldo = 10.0
        saldo += calcular_ec_ganhos(9.0, 5, odd_apostada=2.0, surrealidade=True)
        assert abs(saldo - 30.0) < 0.001

    def test_ciclo_surrealidade_erro(self):
        """
        Palpitou 4-0 (surrealidade), errou (-2 pts), apostou 5 EC
          perde = -5 (igual ao erro normal)
        Saldo: 10 - 5 = 5
        """
        saldo = 10.0
        saldo += calcular_ec_ganhos(-2.0, 5, odd_apostada=2.0)
        assert abs(saldo - 5.0) < 0.001


# ── Regressão: vitória em jogo sem odd (bug ec >= 0) ─────────────────────────

class TestVitoriaOddNula:
    """
    Regressão para o bug onde apostas em jogos sem odd (odd_apostada=None)
    não devolviam o stake ao jogador quando ele vencia.

    Causa: calcular_ec_ganhos retorna 0.0 com odd=1.0 numa vitória.
    O processador usava `if ec > 0` e pulava o crédito — stake sumia.
    Correção: condição trocada para `if ec >= 0`.

    Estes testes validam que:
      1. ec é exatamente 0.0 (sem lucro, mas sem perda) em vitória sem odd.
      2. O ciclo de saldo restaura o stake (saldo_final == saldo_inicial).
      3. Em derrota, ec é negativo — stake não é devolvido.
      4. A lógica de correção manual (3_Resultados) também desfaz corretamente.
    """

    # ── calcular_ec_ganhos com odd None ──────────────────────────────────────

    def test_vencedor_sem_odd_ec_e_zero(self):
        """Vitória (1.5 pts) sem odd → ec == 0.0, não negativo."""
        ec = calcular_ec_ganhos(1.5, 5, odd_apostada=None)
        assert ec == 0.0

    def test_empate_sem_odd_ec_e_zero(self):
        """Empate acertado (3.0 pts) sem odd → ec == 0.0."""
        ec = calcular_ec_ganhos(3.0, 3, odd_apostada=None)
        assert ec == 0.0

    def test_exato_sem_odd_ec_positivo(self):
        """Placar exato (4.5 pts) sem odd → ec > 0 pelo bônus de 50%."""
        ec = calcular_ec_ganhos(4.5, 10, odd_apostada=None)
        # 10 * 1.0 * 1.5 - 10 = 5.0
        assert abs(ec - 5.0) < 0.001

    def test_erro_sem_odd_ec_negativo(self):
        """Derrota sem odd → ec == -valor_apostado (stake perdido)."""
        ec = calcular_ec_ganhos(-1.0, 5, odd_apostada=None)
        assert ec == -5.0

    def test_surrealidade_vencedor_sem_odd_ec_e_zero(self):
        """Surrealidade + vencedor acertado (3.0 pts) sem odd → 0 * 2 == 0."""
        ec = calcular_ec_ganhos(3.0, 4, odd_apostada=None, surrealidade=True)
        assert ec == 0.0

    # ── Ciclo de saldo (simula o if ec >= 0 do processador) ──────────────────

    def _creditar(self, saldo_inicial, aposta, ec):
        """Replica a lógica corrigida: if ec >= 0 → retorna stake + lucro."""
        saldo = saldo_inicial - aposta          # aposta deduzida ao registrar
        if ec >= 0:                             # CONDIÇÃO CORRIGIDA
            saldo += aposta + ec
        # se ec < 0: stake já foi descontado, nada a fazer
        return saldo

    def test_ciclo_vitoria_sem_odd_restaura_stake(self):
        """
        Jogador aposta 5 EC, vence sem odd (ec=0) → saldo final = saldo inicial.
        Com o bug (if ec > 0), o saldo ficaria em saldo_inicial - 5.
        """
        saldo_inicial = 10.0
        aposta = 5.0
        ec = calcular_ec_ganhos(1.5, aposta, odd_apostada=None)  # == 0.0

        saldo_final = self._creditar(saldo_inicial, aposta, ec)
        assert saldo_final == saldo_inicial  # stake devolvido, sem lucro

    def test_ciclo_vitoria_com_odd_aumenta_saldo(self):
        """Controle: vitória com odd 2.0 → saldo aumenta."""
        saldo_inicial = 10.0
        aposta = 5.0
        ec = calcular_ec_ganhos(1.5, aposta, odd_apostada=2.0)  # == 5.0

        saldo_final = self._creditar(saldo_inicial, aposta, ec)
        assert saldo_final == 15.0  # saldo_inicial + lucro

    def test_ciclo_derrota_sem_odd_perde_stake(self):
        """Derrota sem odd → stake perdido; ec < 0 não entra no if."""
        saldo_inicial = 10.0
        aposta = 5.0
        ec = calcular_ec_ganhos(-1.0, aposta, odd_apostada=None)  # == -5.0

        saldo_final = self._creditar(saldo_inicial, aposta, ec)
        assert saldo_final == 5.0  # perdeu o stake

    def test_ciclo_exato_sem_odd_aumenta_saldo_pelo_bonus(self):
        """Placar exato sem odd → bônus de 50% gera lucro > 0."""
        saldo_inicial = 10.0
        aposta = 10.0
        ec = calcular_ec_ganhos(4.5, aposta, odd_apostada=None)  # == 5.0

        saldo_final = self._creditar(saldo_inicial, aposta, ec)
        assert abs(saldo_final - 15.0) < 0.001  # saldo_inicial + bônus

    # ── Lógica de correção manual (3_Resultados.py) ───────────────────────────

    def _desfazer_e_reaplicar(self, saldo, aposta, old_ec, new_ec):
        """
        Replica a lógica de correção manual com a condição corrigida (>= 0).
        Desfaz o EC anterior e aplica o novo.
        """
        if old_ec >= 0:                         # CONDIÇÃO CORRIGIDA
            saldo -= (aposta + old_ec)
        if new_ec >= 0:                         # CONDIÇÃO CORRIGIDA
            saldo += (aposta + new_ec)
        return saldo

    def test_correcao_de_vitoria_sem_odd_para_derrota(self):
        """
        Resultado original: vitória sem odd (ec=0, stake devolvido).
        Correção: placar errado, agora é derrota (ec=-aposta).
        Saldo deve diminuir pelo stake.
        """
        aposta = 5.0
        saldo_apos_resultado = 10.0  # saldo já com stake devolvido (ec=0)

        old_ec = 0.0   # venceu sem odd
        new_ec = -5.0  # agora perdeu

        saldo_final = self._desfazer_e_reaplicar(saldo_apos_resultado, aposta, old_ec, new_ec)
        assert saldo_final == 5.0  # desfez devolução do stake, não recrédita

    def test_correcao_de_derrota_para_vitoria_sem_odd(self):
        """
        Resultado original: derrota (ec=-aposta, stake já perdido).
        Correção: era vitória sem odd (ec=0).
        Saldo deve recuperar o stake.
        """
        aposta = 5.0
        saldo_apos_resultado = 5.0  # saldo após perder stake de 5

        old_ec = -5.0  # perdeu
        new_ec = 0.0   # corrigido: venceu sem odd

        saldo_final = self._desfazer_e_reaplicar(saldo_apos_resultado, aposta, old_ec, new_ec)
        assert saldo_final == 10.0  # stake devolvido


# ── fmt_ec ────────────────────────────────────────────────────────────────────

class TestFmtEc:

    def test_positivo_mostra_sinal(self):
        assert fmt_ec(5.5) == "+5.50 EC"

    def test_negativo_mostra_sinal(self):
        assert fmt_ec(-3.0) == "-3.00 EC"

    def test_zero_sem_sinal(self):
        assert fmt_ec(0) == "0 EC"

    def test_none_retorna_traco(self):
        assert fmt_ec(None) == "—"
