"""
Testes do sistema de ranking: Score = Pontos × Banca disponível.

Regras:
  Banca disponível = saldo_ec − ec_em_jogo  (nunca negativa)
  Score            = total_pontos × banca_disponivel
  Ordenação        : score DESC → total_pontos DESC → placares_exatos DESC
"""

import pytest
from scoring import calcular_score_ranking, ordenar_ranking


# ── calcular_score_ranking ────────────────────────────────────────────────────

class TestCalcularScoreRanking:

    def test_score_basico(self):
        # 10 pts × 15 EC = 150
        assert calcular_score_ranking(10, saldo_ec=15, ec_em_jogo=0) == 150.0

    def test_banca_desconta_em_jogo(self):
        # saldo 20, em jogo 5 → banca 15 → 10 × 15 = 150
        assert calcular_score_ranking(10, saldo_ec=20, ec_em_jogo=5) == 150.0

    def test_banca_nunca_negativa(self):
        # em jogo maior que saldo (inconsistência) → banca = 0 → score = 0
        assert calcular_score_ranking(10, saldo_ec=5, ec_em_jogo=10) == 0.0

    def test_zero_pontos_score_zero(self):
        assert calcular_score_ranking(0, saldo_ec=20, ec_em_jogo=0) == 0.0

    def test_zero_banca_score_zero(self):
        # apostou tudo, banca = 0
        assert calcular_score_ranking(10, saldo_ec=10, ec_em_jogo=10) == 0.0

    def test_score_com_decimais(self):
        # 7 pts × 3.5 EC = 24.5
        assert calcular_score_ranking(7, saldo_ec=3.5, ec_em_jogo=0) == 24.5

    def test_score_arredondado_2_casas(self):
        # 3 pts × 3.333 EC = 9.999 → arredonda para 10.0
        resultado = calcular_score_ranking(3, saldo_ec=3.333, ec_em_jogo=0)
        assert resultado == round(3 * 3.333, 2)

    def test_banca_inicial_10ec(self):
        # Jogador sem apostas: saldo 10, em jogo 0
        # 5 pts × 10 EC = 50
        assert calcular_score_ranking(5, saldo_ec=10, ec_em_jogo=0) == 50.0


# ── ordenar_ranking ───────────────────────────────────────────────────────────

def _jogador(nome, score, pontos, exatos):
    return {"usuario": nome, "score": score, "total_pontos": pontos, "placares_exatos": exatos}


class TestOrdenarRanking:

    def test_maior_score_primeiro(self):
        jogadores = [
            _jogador("B", score=100, pontos=10, exatos=2),
            _jogador("A", score=200, pontos=8,  exatos=1),
        ]
        resultado = ordenar_ranking(jogadores)
        assert resultado[0]["usuario"] == "A"
        assert resultado[1]["usuario"] == "B"

    def test_empate_score_desempata_por_pontos(self):
        jogadores = [
            _jogador("B", score=100, pontos=8,  exatos=3),
            _jogador("A", score=100, pontos=10, exatos=1),
        ]
        resultado = ordenar_ranking(jogadores)
        assert resultado[0]["usuario"] == "A"  # mais pontos

    def test_empate_score_e_pontos_desempata_por_exatos(self):
        jogadores = [
            _jogador("B", score=100, pontos=10, exatos=2),
            _jogador("A", score=100, pontos=10, exatos=5),
        ]
        resultado = ordenar_ranking(jogadores)
        assert resultado[0]["usuario"] == "A"  # mais placares exatos

    def test_tres_jogadores_ordenados(self):
        jogadores = [
            _jogador("C", score=50,  pontos=5,  exatos=1),
            _jogador("A", score=200, pontos=10, exatos=3),
            _jogador("B", score=150, pontos=8,  exatos=2),
        ]
        resultado = ordenar_ranking(jogadores)
        nomes = [j["usuario"] for j in resultado]
        assert nomes == ["A", "B", "C"]

    def test_lista_vazia(self):
        assert ordenar_ranking([]) == []

    def test_um_jogador(self):
        jogadores = [_jogador("A", score=100, pontos=10, exatos=2)]
        resultado = ordenar_ranking(jogadores)
        assert len(resultado) == 1
        assert resultado[0]["usuario"] == "A"

    def test_todos_score_zero(self):
        jogadores = [
            _jogador("B", score=0, pontos=3, exatos=1),
            _jogador("A", score=0, pontos=5, exatos=2),
        ]
        resultado = ordenar_ranking(jogadores)
        assert resultado[0]["usuario"] == "A"  # desempate por pontos

    def test_ordem_nao_alterada_in_place(self):
        # ordenar_ranking deve retornar nova lista, não modificar a original
        original = [
            _jogador("B", score=100, pontos=10, exatos=2),
            _jogador("A", score=200, pontos=8,  exatos=1),
        ]
        copia = list(original)
        ordenar_ranking(original)
        assert original == copia  # lista original intacta


# ── Cenários completos de ranking ─────────────────────────────────────────────

class TestCenariosRanking:

    def _montar(self, nome, pontos, saldo_ec, ec_em_jogo, exatos=0):
        score = calcular_score_ranking(pontos, saldo_ec, ec_em_jogo)
        return _jogador(nome, score=score, pontos=pontos, exatos=exatos)

    def test_mais_pontos_mas_banca_zerada_perde(self):
        """
        Ana: 12 pts, banca 0 EC (apostou tudo e perdeu) → score 0
        Bia: 8 pts,  banca 10 EC                        → score 80
        Bia deve liderar apesar de menos pontos.
        """
        ana = self._montar("Ana", pontos=12, saldo_ec=0,  ec_em_jogo=0)
        bia = self._montar("Bia", pontos=8,  saldo_ec=10, ec_em_jogo=0)
        ranking = ordenar_ranking([ana, bia])
        assert ranking[0]["usuario"] == "Bia"

    def test_gerenciar_banca_compensa(self):
        """
        Carlos: 10 pts × 15 EC = 150
        Diego:  12 pts × 3 EC  = 36
        Carlos lidera mesmo com menos pontos.
        """
        carlos = self._montar("Carlos", pontos=10, saldo_ec=15, ec_em_jogo=0)
        diego  = self._montar("Diego",  pontos=12, saldo_ec=3,  ec_em_jogo=0)
        ranking = ordenar_ranking([diego, carlos])
        assert ranking[0]["usuario"] == "Carlos"

    def test_em_jogo_reduz_banca_para_score(self):
        """
        Eva: 8 pts, saldo 20 EC mas 15 em jogo → banca 5 → score 40
        Fia: 8 pts, saldo 8 EC,  0 em jogo     → banca 8 → score 64
        Fia lidera pois tem mais banca livre.
        """
        eva = self._montar("Eva", pontos=8, saldo_ec=20, ec_em_jogo=15)
        fia = self._montar("Fia", pontos=8, saldo_ec=8,  ec_em_jogo=0)
        ranking = ordenar_ranking([eva, fia])
        assert ranking[0]["usuario"] == "Fia"

    def test_ranking_completo_quatro_jogadores(self):
        """
        Gus: 6 pts × 10 EC  = 60
        Hel: 10 pts × 2 EC  = 20
        Ivo: 4 pts × 20 EC  = 80   ← 1º
        Ju:  8 pts × 7 EC   = 56
        Esperado: Ivo, Gus, Ju, Hel
        """
        gus = self._montar("Gus", pontos=6,  saldo_ec=10, ec_em_jogo=0)
        hel = self._montar("Hel", pontos=10, saldo_ec=2,  ec_em_jogo=0)
        ivo = self._montar("Ivo", pontos=4,  saldo_ec=20, ec_em_jogo=0)
        ju  = self._montar("Ju",  pontos=8,  saldo_ec=7,  ec_em_jogo=0)
        ranking = ordenar_ranking([gus, hel, ivo, ju])
        nomes = [j["usuario"] for j in ranking]
        assert nomes == ["Ivo", "Gus", "Ju", "Hel"]
