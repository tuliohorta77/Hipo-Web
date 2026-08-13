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


# ── Farol semanal ────────────────────────────────────────────────────
#
# HOJE = 12/08/2026 e cai numa QUARTA-FEIRA. A semana dele começa na
# segunda, 10/08. Todo teste abaixo depende disso, então está escrito aqui
# uma vez em vez de repetido em cada assert.

SEGUNDA_DE_HOJE = date(2026, 8, 10)


class TestInicioDaSemana:
    def test_segunda_e_o_proprio_dia(self):
        assert regras.inicio_da_semana(SEGUNDA_DE_HOJE) == SEGUNDA_DE_HOJE

    def test_quarta_volta_para_a_segunda(self):
        assert regras.inicio_da_semana(HOJE) == SEGUNDA_DE_HOJE

    def test_domingo_pertence_a_semana_que_comecou_na_segunda(self):
        """
        A armadilha clássica: em muitos calendários a semana começa no
        domingo, e aí 16/08 abriria uma semana nova. Aqui domingo FECHA a
        semana — quem fez a visita no domingo fez nesta semana.
        """
        assert regras.inicio_da_semana(date(2026, 8, 16)) == SEGUNDA_DE_HOJE

    def test_segunda_seguinte_abre_semana_nova(self):
        assert regras.inicio_da_semana(date(2026, 8, 17)) == date(2026, 8, 17)


class TestSemanasDoFarol:
    def test_devolve_quatro_semanas_por_padrao(self):
        assert len(regras.semanas_do_farol(HOJE)) == regras.SEMANAS_FAROL == 4

    def test_a_corrente_e_a_ultima(self):
        """
        A trilha é lida da esquerda para a direita e termina em hoje.
        Invertida, o olho leria a semana corrente como a mais antiga.
        """
        semanas = regras.semanas_do_farol(HOJE)
        assert semanas[-1] == (SEGUNDA_DE_HOJE, date(2026, 8, 16))
        assert semanas[0] == (date(2026, 7, 20), date(2026, 7, 26))

    def test_semanas_sao_contiguas_e_de_sete_dias(self):
        semanas = regras.semanas_do_farol(HOJE)
        for inicio, fim in semanas:
            assert (fim - inicio).days == 6
        for anterior, seguinte in zip(semanas, semanas[1:]):
            assert (seguinte[0] - anterior[0]).days == 7

    def test_quantidade_zero_e_erro(self):
        with pytest.raises(ValueError):
            regras.semanas_do_farol(HOJE, 0)

    def test_atravessa_a_virada_do_ano(self):
        semanas = regras.semanas_do_farol(date(2026, 1, 7))
        assert semanas[0][0] == date(2025, 12, 15)


class TestCorDoFarol:
    def test_concluida_e_verde(self):
        assert regras.cor_do_farol(concluidas=1, agendadas=0) == "verde"

    def test_concluida_ganha_de_agendada(self):
        """
        Fez e ainda tem outra marcada: a semana é verde. O verde responde
        "houve contato", e houve.
        """
        assert regras.cor_do_farol(concluidas=1, agendadas=3) == "verde"

    def test_so_agendada_e_amarelo(self):
        """
        Agendar dez visitas e não fazer nenhuma não é semana verde. Este é o
        teste que impede o farol de virar medidor de intenção.
        """
        assert regras.cor_do_farol(concluidas=0, agendadas=10) == "amarelo"

    def test_nada_e_vermelho(self):
        assert regras.cor_do_farol(concluidas=0, agendadas=0) == "vermelho"


class TestFarol:
    def test_sem_tarefa_nenhuma_e_quatro_vermelhos(self):
        trilha = regras.farol({}, HOJE)
        assert [s["cor"] for s in trilha] == ["vermelho"] * 4

    def test_semana_ausente_do_dicionario_vira_vermelha(self):
        """
        Quem consulta o banco entrega só as semanas que têm linha. Completar
        os buracos é trabalho do service — sem isso a trilha teria menos de
        quatro casas e a coluna mudaria de largura por linha.
        """
        trilha = regras.farol({SEGUNDA_DE_HOJE: {"concluidas": 2}}, HOJE)
        assert [s["cor"] for s in trilha] == [
            "vermelho", "vermelho", "vermelho", "verde",
        ]

    def test_marca_a_semana_corrente(self):
        trilha = regras.farol({}, HOJE)
        assert [s["corrente"] for s in trilha] == [False, False, False, True]

    def test_leva_as_contagens_para_a_casa_certa(self):
        trilha = regras.farol(
            {
                date(2026, 8, 3): {"concluidas": 0, "agendadas": 1},
                SEGUNDA_DE_HOJE: {"concluidas": 3, "agendadas": 1},
            },
            HOJE,
        )
        assert [s["cor"] for s in trilha] == [
            "vermelho", "vermelho", "amarelo", "verde",
        ]
        assert trilha[-1]["concluidas"] == 3
        assert trilha[-1]["agendadas"] == 1

    def test_ignora_semana_fora_da_janela(self):
        """
        Contagem de uma semana que não está na trilha não vaza para nenhuma
        casa. Chave desconhecida é chave desconhecida.
        """
        trilha = regras.farol({date(2026, 6, 1): {"concluidas": 9}}, HOJE)
        assert [s["cor"] for s in trilha] == ["vermelho"] * 4


class TestSemContatoNaSemana:
    def test_vermelho_na_corrente_pede_acao(self):
        assert regras.sem_contato_na_semana(regras.farol({}, HOJE)) is True

    def test_verde_na_corrente_nao_pede(self):
        trilha = regras.farol({SEGUNDA_DE_HOJE: {"concluidas": 1}}, HOJE)
        assert regras.sem_contato_na_semana(trilha) is False

    def test_amarelo_na_corrente_fica_fora_da_fila(self):
        """
        Já tem tarefa marcada com alguém. Um KPI que cobra quem já agendou
        vira ruído que se aprende a ignorar.
        """
        trilha = regras.farol({SEGUNDA_DE_HOJE: {"agendadas": 1}}, HOJE)
        assert regras.sem_contato_na_semana(trilha) is False

    def test_semana_passada_verde_nao_salva_a_corrente(self):
        """
        O KPI é sobre ESTA semana. Ter falado na semana passada não tira
        ninguém da fila de hoje.
        """
        trilha = regras.farol({date(2026, 8, 3): {"concluidas": 5}}, HOJE)
        assert regras.sem_contato_na_semana(trilha) is True


class TestSemanasSemContato:
    def test_tudo_vermelho_conta_a_trilha_inteira(self):
        assert regras.semanas_sem_contato(regras.farol({}, HOJE)) == 4

    def test_verde_na_corrente_zera(self):
        trilha = regras.farol({SEGUNDA_DE_HOJE: {"concluidas": 1}}, HOJE)
        assert regras.semanas_sem_contato(trilha) == 0

    def test_conta_de_tras_para_frente_e_para_no_primeiro_verde(self):
        """
        Verde há três semanas e nada desde então: são 3 semanas sem contato,
        não 1. É a leitura de gravidade que a cor sozinha não dá.
        """
        trilha = regras.farol({date(2026, 7, 20): {"concluidas": 1}}, HOJE)
        assert regras.semanas_sem_contato(trilha) == 3

    def test_amarelo_conta_como_sem_contato(self):
        """
        Amarelo é promessa, não contato. Quem só agenda há um mês está há um
        mês sem falar com o parceiro.
        """
        trilha = regras.farol(
            {s[0]: {"agendadas": 1} for s in regras.semanas_do_farol(HOJE)}, HOJE
        )
        assert regras.semanas_sem_contato(trilha) == 4
