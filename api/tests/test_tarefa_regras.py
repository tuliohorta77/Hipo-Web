"""
HIPO — Testes das regras de tarefa (funções puras, sem banco).

Duas regras que estes testes documentam e travam:

  1. A situação é derivada de prazo + carimbos + relógio. Nada é guardado.
  2. Concluir exige a próxima tarefa enquanto a oportunidade está viva.

Todo teste passa `agora` explicitamente. Nenhum mock de tempo, nenhum teste
que quebra à meia-noite ou na virada do ano.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import tarefa as regras
from services.tarefa import (
    ORDEM_SITUACAO,
    ROTULOS_TIPO,
    SITUACOES,
    SITUACOES_ABERTAS,
    TIPOS,
    EstadoTarefa,
    TarefaInvalida,
    chave_ordenacao,
    esta_aberta,
    exige_proxima,
    situacao,
    validar_cancelamento,
    validar_conclusao,
    validar_edicao,
    validar_tipo,
)

AGORA = datetime(2026, 8, 10, 14, 30, tzinfo=timezone.utc)


def aberta(prazo):
    return EstadoTarefa(prazo=prazo)


# ── Vocabulário ──────────────────────────────────────────────────────

class TestVocabulario:
    def test_tipos_sao_lista_fechada(self):
        """
        Diferente de vertical e origem, o tipo NÃO é criável pelo usuário:
        comparar "quantas ligações até fechar" só funciona com vocabulário
        estável.
        """
        assert TIPOS == (
            "ligacao", "reuniao", "visita", "proposta",
            "email", "whatsapp", "outro",
        )

    def test_todo_tipo_tem_rotulo(self):
        assert set(ROTULOS_TIPO) == set(TIPOS)

    def test_situacoes_abertas_sao_as_tres_primeiras(self):
        assert SITUACOES_ABERTAS == ("atrasada", "hoje", "futura")
        assert "concluida" not in SITUACOES_ABERTAS
        assert "cancelada" not in SITUACOES_ABERTAS

    def test_validar_tipo_recusa_desconhecido(self):
        assert validar_tipo("ligacao") == "ligacao"
        with pytest.raises(TarefaInvalida, match="Tipo de tarefa inválido"):
            validar_tipo("cafezinho")


# ── Situação derivada ────────────────────────────────────────────────

class TestSituacao:
    def test_prazo_amanha_e_futura(self):
        assert situacao(aberta(AGORA + timedelta(days=1)), AGORA) == "futura"

    def test_prazo_ontem_e_atrasada(self):
        assert situacao(aberta(AGORA - timedelta(days=1)), AGORA) == "atrasada"

    def test_prazo_no_mesmo_dia_e_hoje(self):
        assert situacao(aberta(AGORA + timedelta(hours=2)), AGORA) == "hoje"

    def test_passou_da_hora_mas_nao_do_dia_ainda_e_hoje(self):
        """
        Regra deliberada: 'hoje' é dia de calendário, não janela de 24h. Uma
        tarefa das 09h continua sendo de hoje às 18h — ainda dá para fazer. O
        que passou do DIA é dívida, e aí sim vira atrasada.
        """
        manha = AGORA.replace(hour=9, minute=0)
        assert situacao(aberta(manha), AGORA) == "hoje"

    def test_o_dia_e_o_do_fuso_da_operacao_nao_o_de_utc(self):
        """
        Regressao real: uma tarefa marcada para 21h de Brasilia e 00h do dia
        SEGUINTE em UTC. Comparando em UTC ela virava 'futura' e sumia da
        coluna de hoje as 18h, justamente quando o vendedor mais olha.
        """
        # 08/08 as 21h em Brasilia = 09/08 00:00 UTC.
        prazo = datetime(2026, 8, 9, 0, 0, tzinfo=timezone.utc)
        # 08/08 as 15h em Brasilia = 18:00 UTC.
        agora = datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc)
        assert situacao(aberta(prazo), agora) == "hoje"

    def test_madrugada_em_utc_ainda_e_o_dia_anterior_aqui(self):
        """
        02h UTC do dia 9 = 23h do dia 8 em Brasilia. Uma tarefa do dia 8
        continua sendo de hoje.
        """
        prazo = datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc)   # 15h BRT dia 8
        agora = datetime(2026, 8, 9, 2, 0, tzinfo=timezone.utc)    # 23h BRT dia 8
        assert situacao(aberta(prazo), agora) == "hoje"

    def test_um_minuto_depois_da_meia_noite_vira_atrasada(self):
        # 00:01 de Brasilia = 03:01 UTC.
        ontem_tarde = AGORA - timedelta(days=1)
        logo_depois = AGORA.replace(hour=3, minute=1)
        assert situacao(aberta(ontem_tarde), logo_depois) == "atrasada"

    def test_concluida_ignora_o_prazo(self):
        """Tarefa concluída atrasada é concluída, não atrasada."""
        e = EstadoTarefa(prazo=AGORA - timedelta(days=30), concluida_em=AGORA)
        assert situacao(e, AGORA) == "concluida"

    def test_cancelada_ignora_o_prazo(self):
        e = EstadoTarefa(prazo=AGORA - timedelta(days=30), cancelada_em=AGORA)
        assert situacao(e, AGORA) == "cancelada"

    def test_prazo_sem_fuso_nao_explode(self):
        """
        asyncpg devolve com fuso, teste puro costuma montar ingênuo. Comparar
        os dois levantaria TypeError — a normalização evita isso.
        """
        ingenuo = datetime(2026, 8, 11, 10, 0)
        assert situacao(aberta(ingenuo), AGORA) == "futura"

    def test_toda_situacao_esta_no_vocabulario(self):
        for prazo in (AGORA - timedelta(days=2), AGORA, AGORA + timedelta(days=2)):
            assert situacao(aberta(prazo), AGORA) in SITUACOES

    def test_esta_aberta(self):
        assert esta_aberta(aberta(AGORA))
        assert not esta_aberta(EstadoTarefa(prazo=AGORA, concluida_em=AGORA))
        assert not esta_aberta(EstadoTarefa(prazo=AGORA, cancelada_em=AGORA))


# ── Próxima tarefa obrigatória ───────────────────────────────────────

class TestExigeProxima:
    def test_oportunidade_ativa_exige(self):
        assert exige_proxima("ativa")

    def test_suspensa_tambem_exige(self):
        """
        Suspender é pausa. Pausa sem data para voltar é como oportunidade
        morre em silêncio.
        """
        assert exige_proxima("suspensa")

    @pytest.mark.parametrize("status", ["conquistado", "perdido", "cancelado"])
    def test_finalizada_nao_exige(self, status):
        assert not exige_proxima(status)


class TestValidarConclusao:
    def test_ativa_sem_proxima_e_recusada(self):
        with pytest.raises(TarefaInvalida, match="agendar a próxima tarefa"):
            validar_conclusao(aberta(AGORA), "ativa", tem_proxima=False)

    def test_ativa_com_proxima_passa(self):
        validar_conclusao(aberta(AGORA), "ativa", tem_proxima=True)

    def test_finalizada_sem_proxima_passa(self):
        validar_conclusao(aberta(AGORA), "conquistado", tem_proxima=False)

    def test_mensagem_diz_o_que_fazer(self):
        """
        Erro que só diz 'inválido' faz o usuário chutar. Este diz a saída:
        finalizar a oportunidade.
        """
        with pytest.raises(TarefaInvalida) as e:
            validar_conclusao(aberta(AGORA), "ativa", tem_proxima=False)
        assert "finalize a oportunidade" in str(e.value).lower()

    def test_nao_conclui_duas_vezes(self):
        e = EstadoTarefa(prazo=AGORA, concluida_em=AGORA)
        with pytest.raises(TarefaInvalida, match="já foi concluída"):
            validar_conclusao(e, "ativa", tem_proxima=True)

    def test_nao_conclui_cancelada(self):
        e = EstadoTarefa(prazo=AGORA, cancelada_em=AGORA)
        with pytest.raises(TarefaInvalida, match="foi cancelada"):
            validar_conclusao(e, "ativa", tem_proxima=True)


class TestValidarCancelamento:
    def test_aberta_pode_cancelar(self):
        validar_cancelamento(aberta(AGORA))

    def test_concluida_nao_pode(self):
        e = EstadoTarefa(prazo=AGORA, concluida_em=AGORA)
        with pytest.raises(TarefaInvalida, match="não pode ser cancelada"):
            validar_cancelamento(e)

    def test_nao_cancela_duas_vezes(self):
        e = EstadoTarefa(prazo=AGORA, cancelada_em=AGORA)
        with pytest.raises(TarefaInvalida, match="já foi cancelada"):
            validar_cancelamento(e)


class TestValidarEdicao:
    def test_aberta_e_editavel(self):
        validar_edicao(aberta(AGORA))

    @pytest.mark.parametrize("campo", ["concluida_em", "cancelada_em"])
    def test_fechada_nao_e_editavel(self, campo):
        """
        Reescrever prazo ou título de tarefa fechada apagaria o histórico —
        que é justamente o que a aba existe para mostrar.
        """
        e = EstadoTarefa(prazo=AGORA, **{campo: AGORA})
        with pytest.raises(TarefaInvalida, match="histórico é imutável"):
            validar_edicao(e)


# ── Ordenação ────────────────────────────────────────────────────────

class TestOrdenacao:
    def test_atrasada_vem_antes_de_tudo(self):
        assert ORDEM_SITUACAO["atrasada"] < ORDEM_SITUACAO["hoje"]
        assert ORDEM_SITUACAO["hoje"] < ORDEM_SITUACAO["futura"]
        assert ORDEM_SITUACAO["futura"] < ORDEM_SITUACAO["concluida"]

    def test_ordena_por_bloco_e_depois_por_prazo(self):
        itens = [
            ("futura", AGORA + timedelta(days=5)),
            ("atrasada", AGORA - timedelta(days=1)),
            ("concluida", AGORA - timedelta(days=10)),
            ("atrasada", AGORA - timedelta(days=9)),
            ("hoje", AGORA),
        ]
        ordenado = sorted(itens, key=lambda i: chave_ordenacao(*i))
        assert [s for s, _ in ordenado] == [
            "atrasada", "atrasada", "hoje", "futura", "concluida",
        ]
        # Dentro do bloco atrasada, a mais antiga primeiro.
        assert ordenado[0][1] < ordenado[1][1]

    def test_prazo_ingenuo_nao_quebra_a_ordenacao(self):
        itens = [("hoje", datetime(2026, 8, 10, 9, 0)), ("hoje", AGORA)]
        assert len(sorted(itens, key=lambda i: chave_ordenacao(*i))) == 2


# ── O alvo da tarefa (006) ───────────────────────────────────────────
#
# Toda tarefa é de uma oportunidade OU de um parceiro. Zero alvos seria a
# lista de afazeres pessoal que a Sprint 5 recusou; dois alvos faria a
# primeira métrica que somasse os dois contar a mesma tarefa duas vezes.

class TestValidarAlvo:
    def test_so_oportunidade(self):
        assert regras.validar_alvo("opp-1", None) == "oportunidade"

    def test_so_parceiro(self):
        assert regras.validar_alvo(None, "conta-1") == "parceiro"

    def test_os_dois_e_recusado(self):
        with pytest.raises(regras.TarefaInvalida, match="não das duas"):
            regras.validar_alvo("opp-1", "conta-1")

    def test_nenhum_e_recusado(self):
        with pytest.raises(regras.TarefaInvalida, match="Informe a oportunidade"):
            regras.validar_alvo(None, None)

    def test_todo_alvo_devolvido_esta_na_lista(self):
        for retorno in (
            regras.validar_alvo("opp-1", None),
            regras.validar_alvo(None, "conta-1"),
        ):
            assert retorno in regras.ALVOS
            assert retorno in regras.ROTULOS_ALVO


class TestExigeProximaNoParceiro:
    def test_tarefa_de_parceiro_nao_exige(self):
        """
        `status_oportunidade` chega None quando a tarefa é de parceiro.

        A regra da oportunidade se apoia num estado final: um dia ela é
        conquistada ou perdida e a corrente termina. Parceria não tem estado
        final — exigir a próxima ali produziria corrente infinita, e o que se
        agenda para não deixar o campo vazio é justamente a tarefa que
        ninguém faz. Quem cobra cadência do parceiro é o farol semanal.
        """
        assert regras.exige_proxima(None) is False

    def test_conclusao_de_tarefa_de_parceiro_passa_sem_proxima(self):
        estado = EstadoTarefa(prazo=datetime(2026, 8, 12, 9, tzinfo=timezone.utc))
        regras.validar_conclusao(estado, None, tem_proxima=False)

    def test_conclusao_de_tarefa_de_parceiro_aceita_proxima(self):
        """Não é obrigatória, mas continua sendo aceita."""
        estado = EstadoTarefa(prazo=datetime(2026, 8, 12, 9, tzinfo=timezone.utc))
        regras.validar_conclusao(estado, None, tem_proxima=True)
