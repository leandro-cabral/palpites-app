"""
Testes das regras de negócio: pontuação e cálculo de EC (Elevação Coin).

Regras:
  Pontuação
    3 pts — placar exato
    2 pts — empate acertado (placar diferente)
    1 pt  — vencedor correto (placar diferente)
    0 pts — erro
    None  — jogo sem resultado real

  EC (calcular_ec_ganhos)
    Sem aposta           → 0.0
    Erro (0 pts)         → -valor_apostado
    Acerto 1 ou 2 pts    → valor × odd − valor   (lucro líquido)
    Placar exato (3 pts) → valor × odd × 1.5 − valor  (bônus 50%)
"""

import pytest
from scoring import calcular_pontos, calcular_ec_ganhos, fmt_ec


# ── calcular_pontos ───────────────────────────────────────────────────────────

class TestCalcularPontos:

    # Placar exato
    def test_placar_exato_vitoria_casa(self):
        assert calcular_pontos(2, 1, 2, 1) == 3

    def test_placar_exato_vitoria_fora(self):
        assert calcular_pontos(0, 3, 0, 3) == 3

    def test_placar_exato_empate(self):
        assert calcular_pontos(1, 1, 1, 1) == 3

    def test_placar_exato_0x0(self):
        assert calcular_pontos(0, 0, 0, 0) == 3

    # Empate acertado (placar diferente)
    def test_empate_acertado_placar_diferente(self):
        assert calcular_pontos(2, 2, 1, 1) == 2

    def test_empate_acertado_outro_placar(self):
        assert calcular_pontos(0, 0, 3, 3) == 2

    # Vencedor correto (placar diferente)
    def test_vencedor_casa_correto(self):
        assert calcular_pontos(2, 0, 3, 1) == 1

    def test_vencedor_fora_correto(self):
        assert calcular_pontos(0, 1, 0, 4) == 1

    def test_vencedor_casa_placar_bem_diferente(self):
        assert calcular_pontos(1, 0, 5, 0) == 1

    # Erro
    def test_errou_resultado_oposto(self):
        assert calcular_pontos(2, 1, 0, 1) == 0

    def test_errou_empate_esperado_vitoria_real(self):
        assert calcular_pontos(1, 1, 2, 0) == 0

    def test_errou_vitoria_esperada_empate_real(self):
        assert calcular_pontos(3, 1, 2, 2) == 0

    # Sem resultado real
    def test_sem_resultado_retorna_none(self):
        assert calcular_pontos(1, 0, None, None) is None

    def test_resultado_parcialmente_none(self):
        assert calcular_pontos(1, 0, 1, None) is None


# ── calcular_ec_ganhos ────────────────────────────────────────────────────────

class TestCalcularEcGanhos:

    # Sem aposta
    def test_sem_aposta_zero_retorna_zero(self):
        assert calcular_ec_ganhos(3, 0) == 0.0

    def test_sem_aposta_none_retorna_zero(self):
        assert calcular_ec_ganhos(1, None) == 0.0

    # Erro (0 pts) — perde o apostado
    def test_erro_perde_aposta_inteira(self):
        assert calcular_ec_ganhos(0, 5) == -5.0

    def test_erro_perde_aposta_decimal(self):
        assert calcular_ec_ganhos(0, 3.5) == -3.5

    def test_erro_perde_com_odd_alta(self):
        # Odd não importa se errou — perde o valor apostado
        assert calcular_ec_ganhos(0, 10, odd_apostada=5.0) == -10.0

    # Acerto simples (1 ou 2 pts): lucro = valor × odd − valor
    def test_acerto_vencedor_odd_2(self):
        # apostou 10 na vitória com odd 2.0 → lucro = 10*2 - 10 = 10
        resultado = calcular_ec_ganhos(1, 10, odd_apostada=2.0)
        assert abs(resultado - 10.0) < 0.001

    def test_acerto_empate_odd_3(self):
        # apostou 5 no empate com odd 3.0 → lucro = 5*3 - 5 = 10
        resultado = calcular_ec_ganhos(2, 5, odd_apostada=3.0)
        assert abs(resultado - 10.0) < 0.001

    def test_acerto_vencedor_odd_1_5(self):
        # apostou 4 com odd 1.5 → lucro = 4*1.5 - 4 = 2
        resultado = calcular_ec_ganhos(1, 4, odd_apostada=1.5)
        assert abs(resultado - 2.0) < 0.001

    def test_acerto_sem_odd_usa_odd_1(self):
        # Sem odd definida → usa 1.0 → lucro = valor*1 - valor = 0
        resultado = calcular_ec_ganhos(1, 5, odd_apostada=None)
        assert abs(resultado - 0.0) < 0.001

    # Placar exato (3 pts): bônus 50% → lucro = valor × odd × 1.5 − valor
    def test_exato_bonus_50pct_odd_2(self):
        # apostou 10 com odd 2.0 → lucro = 10*2*1.5 - 10 = 20
        resultado = calcular_ec_ganhos(3, 10, odd_apostada=2.0)
        assert abs(resultado - 20.0) < 0.001

    def test_exato_bonus_50pct_odd_3(self):
        # apostou 4 com odd 3.0 → lucro = 4*3*1.5 - 4 = 14
        resultado = calcular_ec_ganhos(3, 4, odd_apostada=3.0)
        assert abs(resultado - 14.0) < 0.001

    def test_exato_sem_odd_usa_odd_1(self):
        # odd=None → 1.0 → lucro = 10*1*1.5 - 10 = 5
        resultado = calcular_ec_ganhos(3, 10, odd_apostada=None)
        assert abs(resultado - 5.0) < 0.001

    # Coerência: exato sempre rende mais que acerto simples na mesma odd
    def test_exato_rende_mais_que_acerto_simples(self):
        aposta, odd = 10, 2.5
        ec_exato  = calcular_ec_ganhos(3, aposta, odd_apostada=odd)
        ec_simples = calcular_ec_ganhos(1, aposta, odd_apostada=odd)
        assert ec_exato > ec_simples

    # Valores decimais precisos (sem arredondamento)
    def test_sem_arredondamento(self):
        resultado = calcular_ec_ganhos(1, 7, odd_apostada=1.85)
        esperado  = 7 * 1.85 - 7  # = 5.95
        assert abs(resultado - esperado) < 0.0001


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
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=1, odd=2.0)
        assert saldo_final == 15.0  # lucro = 5*2 - 5 = 5

    def test_ciclo_perdeu_saldo_diminui(self):
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=0, odd=2.0)
        assert saldo_final == 5.0  # perde 5

    def test_ciclo_exato_saldo_aumenta_mais(self):
        saldo_final = self._novo_saldo(10.0, aposta=5, pontos=3, odd=2.0)
        assert saldo_final == 20.0  # lucro = 5*2*1.5 - 5 = 10

    def test_ciclo_sem_aposta_saldo_inalterado(self):
        saldo_final = self._novo_saldo(10.0, aposta=0, pontos=3, odd=2.0)
        assert saldo_final == 10.0

    def test_ciclo_multiplos_jogos(self):
        """
        Jogo A: apostou 3 EC @ odd 2.0, acertou vencedor (1 pt)
          → lucro = 3*2 - 3 = 3
        Jogo B: apostou 2 EC @ odd 3.2, errou
          → perde = -2
        Jogo C: apostou 4 EC @ odd 1.8, acertou placar exato (3 pts)
          → lucro = 4*1.8*1.5 - 4 = 6.8
        Saldo inicial: 10 → esperado: 10 + 3 - 2 + 6.8 = 17.8
        """
        saldo = 10.0
        saldo += calcular_ec_ganhos(1, 3, odd_apostada=2.0)
        saldo += calcular_ec_ganhos(0, 2, odd_apostada=3.2)
        saldo += calcular_ec_ganhos(3, 4, odd_apostada=1.8)
        assert abs(saldo - 17.8) < 0.001


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
