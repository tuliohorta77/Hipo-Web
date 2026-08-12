"""
Regras da carteira de parceiros — testes puros, sem banco.

O relógio entra por parâmetro (`hoje`), então nada aqui depende do dia em que
a suíte roda. É o mesmo padrão de test_tarefa_regras.py, e existe pelo mesmo
motivo: teste que muda de resultado conforme a data não é teste.
"""
from datetime import date

import pytest

from services import parceiro as regras


HOJE = date(2026, 8, 12)


# ── Períodos ─────────────────────────────────────────────────────────

class TestInicioDoPeriodo:
    def test_sempre_nao_tem_inicio(self):
        """
        None não é ausência de resposta: é a resposta. O SQL usa
        ($n IS NULL OR criado_em >= $n), então 'sempre' vira um filtro que
        não filtra — e a consulta continua sendo uma só.
        """
        assert regras.inicio_do_periodo("sempre", HOJE) is None

    def test_90_dias_conta_para_tras(self):
        assert regras.inicio_do_periodo("90d", HOJE) == date(2026, 5, 14)

    def test_ano_comeca_em_primeiro_de_janeiro(self):
        assert regras.inicio_do_periodo("ano", HOJE) == date(2026, 1, 1)

    def test_ano_no_primeiro_dia_do_ano(self):
        assert regras.inicio_do_periodo("ano", date(2026, 1, 1)) == date(2026, 1, 1)

    def test_90d_atravessa_a_virada_do_ano(self):
        assert regras.inicio_do_periodo("90d", date(2026, 2, 1)) == date(2025, 11, 3)

    def test_periodo_invalido_levanta(self):
        with pytest.raises(ValueError, match="Período inválido"):
            regras.inicio_do_periodo("decada", HOJE)

    def test_todos_os_periodos_declarados_funcionam(self):
        """Guarda contra alguém adicionar um período em PERIODOS e esquecer
        de ensinar inicio_do_periodo a calculá-lo."""
        for p in regras.PERIODOS:
            regras.inicio_do_periodo(p, HOJE)

    def test_todo_periodo_tem_rotulo(self):
        assert set(regras.ROTULOS_PERIODO) == set(regras.PERIODOS)


# ── Situação da relação ──────────────────────────────────────────────

class TestSituacao:
    def test_sem_indicacao_nenhuma(self):
        assert regras.situacao(None, HOJE) == "sem_indicacao"

    def test_indicou_hoje_e_ativo(self):
        assert regras.situacao(HOJE, HOJE) == "ativo"

    def test_limite_de_ativo_e_inclusivo(self):
        """90 dias exatos ainda é ativo. O corte precisa ser em um lado só —
        senão existe um dia sem classificação."""
        limite = date(2026, 5, 14)   # 90 dias antes de HOJE
        assert (HOJE - limite).days == 90
        assert regras.situacao(limite, HOJE) == "ativo"

    def test_um_dia_depois_do_limite_esfria(self):
        assert regras.situacao(date(2026, 5, 13), HOJE) == "esfriando"

    def test_limite_de_esfriando_e_inclusivo(self):
        limite = date(2026, 2, 13)   # 180 dias antes de HOJE
        assert (HOJE - limite).days == 180
        assert regras.situacao(limite, HOJE) == "esfriando"

    def test_passou_de_180_dias_dorme(self):
        assert regras.situacao(date(2026, 2, 12), HOJE) == "dormente"

    def test_indicacao_muito_antiga_dorme(self):
        assert regras.situacao(date(2023, 1, 1), HOJE) == "dormente"

    def test_todas_as_situacoes_tem_rotulo(self):
        assert set(regras.ROTULOS_SITUACAO) == set(regras.SITUACOES)

    def test_todas_as_situacoes_tem_ordem(self):
        assert set(regras.ORDEM_SITUACAO) == set(regras.SITUACOES)

    def test_ordem_poe_quem_precisa_de_acao_na_frente(self):
        """
        A ordem é de ATENÇÃO, não alfabética nem cronológica. Parceiro que
        nunca indicou vem antes do dormente: é promessa não cumprida, e
        normalmente é mais barato ativar do que ressuscitar.
        """
        o = regras.ORDEM_SITUACAO
        assert o["sem_indicacao"] < o["dormente"] < o["esfriando"] < o["ativo"]

    def test_validar_situacao_aceita_as_conhecidas(self):
        for s in regras.SITUACOES:
            assert regras.validar_situacao(s) == s

    def test_validar_situacao_recusa_invento(self):
        with pytest.raises(ValueError, match="Situação inválida"):
            regras.validar_situacao("morno")


# ── Taxa de conversão ────────────────────────────────────────────────

class TestTaxaConversao:
    def test_metade_converteu(self):
        assert regras.taxa_conversao(conquistadas=2, perdidas=2) == 0.5

    def test_tudo_converteu(self):
        assert regras.taxa_conversao(conquistadas=3, perdidas=0) == 1.0

    def test_nada_converteu(self):
        assert regras.taxa_conversao(conquistadas=0, perdidas=4) == 0.0

    def test_sem_nada_fechado_devolve_none(self):
        """
        0% e "ainda não deu para saber" são coisas diferentes. Mostrar 0%
        para o parceiro que indicou ontem é mentira — e é a leitura que faria
        alguém cobrar quem não deve nada.
        """
        assert regras.taxa_conversao(conquistadas=0, perdidas=0) is None

    def test_cancelado_nao_entra_no_denominador(self):
        """
        Cancelado é erro nosso de CRM. Punir o parceiro por lead que a gente
        cadastrou errado inverteria o sentido do indicador — e a qualidade da
        indicação já é medida separado, pela taxa de cancelamento.
        """
        # A assinatura não aceita canceladas: é a garantia estrutural.
        assert regras.taxa_conversao(1, 1) == 0.5

    def test_arredonda_para_quatro_casas(self):
        assert regras.taxa_conversao(1, 2) == 0.3333


# ── Taxa de cancelamento ─────────────────────────────────────────────

class TestTaxaCancelamento:
    def test_um_de_quatro(self):
        assert regras.taxa_cancelamento(canceladas=1, indicacoes=4) == 0.25

    def test_sem_indicacao_devolve_none(self):
        assert regras.taxa_cancelamento(canceladas=0, indicacoes=0) is None

    def test_nenhum_cancelamento_e_zero_e_nao_none(self):
        """
        Aqui zero é resposta de verdade: o parceiro indicou e nada foi
        cancelado. Diferente da conversão, o denominador já existe.
        """
        assert regras.taxa_cancelamento(canceladas=0, indicacoes=5) == 0.0

    def test_denominador_inclui_o_que_esta_em_aberto(self):
        """
        Conversão mede o que aconteceu com o negócio; cancelamento mede o que
        o parceiro entregou. Por isso os denominadores são diferentes: aqui
        entra tudo que ele indicou, inclusive o que ainda está em aberto.
        """
        # 10 indicações, 2 canceladas, o resto em aberto -> 20%.
        assert regras.taxa_cancelamento(2, 10) == 0.2
