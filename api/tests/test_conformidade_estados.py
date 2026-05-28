"""
HIPO — Testes da regra de 3 estados da conformidade (v1.3.2).

Cobre o estado de ATENÇÃO (tarefa para hoje) introduzido no serviço
vendas_cromie. A régua é compartilhada por Vendas e Agendamento.

Regra (Opção A):
  - tarefa_futura=1                         -> conforme (não olha data)
  - tarefa_futura=0 e ult_prox_tarefa=hoje  -> atenção (se for o único pendente)
  - tarefa_futura=0 e data passada/ausente  -> problema
  - tarefa hoje + outro problema            -> problema, com tarefa_hoje=True

'hoje' é injetado para determinismo.
"""
from datetime import date, datetime

from services.vendas_cromie import (
    classificar_oportunidade,
    resumir_funil,
    ESTADO_CONFORME,
    ESTADO_ATENCAO,
    ESTADO_PROBLEMA,
    REGRA_TAREFA_FUTURA,
    REGRA_TEMPERATURA,
)


HOJE = date(2026, 5, 28)
ONTEM = date(2026, 5, 27)
AMANHA = date(2026, 5, 29)


def _op(fase, *, tf=0, upt=None, temp=None, prev="Não", ticket="Não"):
    """upt aceita date, datetime, string ISO ou None."""
    return {
        "fase": fase,
        "tarefa_futura": tf,
        "ult_prox_tarefa": upt,
        "temperatura": temp,
        "previsao_preenchido": prev,
        "ticket_preenchido": ticket,
    }


class TestEstadoAtencao:
    def test_suspect_tarefa_hoje_e_atencao(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=0, upt=HOJE), hoje=HOJE)
        assert cls["estado"] == ESTADO_ATENCAO
        assert cls["tarefa_hoje"] is True
        assert cls["conforme"] is False
        # A regra de tarefa foi neutralizada — não aparece como problema.
        assert REGRA_TAREFA_FUTURA not in cls["problemas"]

    def test_suspect_tarefa_hoje_via_datetime(self):
        # ult_prox_tarefa costuma vir como datetime (TIMESTAMPTZ).
        dt = datetime(2026, 5, 28, 14, 30)
        cls = classificar_oportunidade(_op("01. Suspect", tf=0, upt=dt), hoje=HOJE)
        assert cls["estado"] == ESTADO_ATENCAO

    def test_suspect_tarefa_hoje_via_string_iso(self):
        cls = classificar_oportunidade(
            _op("01. Suspect", tf=0, upt="2026-05-28T09:00:00"), hoje=HOJE
        )
        assert cls["estado"] == ESTADO_ATENCAO

    def test_tarefa_futura_de_verdade_e_conforme(self):
        # tf=1: o dado garante que é futura; não precisa olhar a data.
        cls = classificar_oportunidade(_op("01. Suspect", tf=1, upt=None), hoje=HOJE)
        assert cls["estado"] == ESTADO_CONFORME
        assert cls["conforme"] is True
        assert cls["tarefa_hoje"] is False

    def test_tarefa_vencida_e_problema(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=0, upt=ONTEM), hoje=HOJE)
        assert cls["estado"] == ESTADO_PROBLEMA
        assert cls["tarefa_hoje"] is False
        assert REGRA_TAREFA_FUTURA in cls["problemas"]

    def test_sem_tarefa_e_problema(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=0, upt=None), hoje=HOJE)
        assert cls["estado"] == ESTADO_PROBLEMA
        assert cls["tarefa_hoje"] is False

    def test_data_futura_mas_tf_zero_e_problema(self):
        # Borda: data no futuro mas tarefa_futura=0. Não é "hoje", então
        # a regra de tarefa não é neutralizada -> problema.
        cls = classificar_oportunidade(_op("01. Suspect", tf=0, upt=AMANHA), hoje=HOJE)
        assert cls["estado"] == ESTADO_PROBLEMA


class TestAtencaoComOutrosProblemas:
    def test_negociacao_tarefa_hoje_mas_sem_temperatura_e_problema(self):
        # Opção A: tarefa hoje neutraliza só a tarefa; falta de temperatura
        # mantém vermelho, mas o badge tarefa_hoje aparece.
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=0, upt=HOJE, temp=None, prev="Sim", ticket="Sim"),
            hoje=HOJE,
        )
        assert cls["estado"] == ESTADO_PROBLEMA
        assert cls["tarefa_hoje"] is True
        assert REGRA_TEMPERATURA in cls["problemas"]
        assert REGRA_TAREFA_FUTURA not in cls["problemas"]

    def test_negociacao_tarefa_hoje_e_tudo_ok_e_atencao(self):
        cls = classificar_oportunidade(
            _op("05. Negociação", tf=0, upt=HOJE, temp=90, prev="Sim", ticket="Sim"),
            hoje=HOJE,
        )
        assert cls["estado"] == ESTADO_ATENCAO
        assert cls["tarefa_hoje"] is True


class TestResumoAtencaoHoje:
    def test_atencao_fica_fora_do_percentual(self):
        ops = [
            _op("01. Suspect", tf=1),             # conforme
            _op("01. Suspect", tf=0, upt=HOJE),   # atenção
            _op("01. Suspect", tf=0, upt=ONTEM),  # problema
            _op("06. Conquistado", tf=1),         # fora da análise
        ]
        r = resumir_funil(ops, hoje=HOJE)["resumo"]
        assert r["conformes"] == 1
        assert r["nao_conformes"] == 1
        assert r["atencao_hoje"] == 1
        # total_analisadas NÃO inclui atenção.
        assert r["total_analisadas"] == 2
        # pct = 1 / (1 + 1) = 50% (atenção não conta no denominador).
        assert r["pct_conforme"] == 50.0

    def test_por_fase_conta_atencao(self):
        ops = [_op("01. Suspect", tf=0, upt=HOJE)]
        por_fase = resumir_funil(ops, hoje=HOJE)["por_fase"]
        assert por_fase["01. Suspect"]["atencao"] == 1
        assert por_fase["01. Suspect"]["total"] == 1

    def test_resumo_tem_campo_atencao_hoje(self):
        r = resumir_funil([], hoje=HOJE)["resumo"]
        assert "atencao_hoje" in r
        assert r["atencao_hoje"] == 0


class TestRetrocompatibilidade:
    def test_tf1_sem_data_continua_conforme(self):
        # Garante que o comportamento antigo (tf=1, sem ult_prox_tarefa)
        # segue conforme — base dos testes pré-v1.3.2.
        cls = classificar_oportunidade(_op("01. Suspect", tf=1))
        assert cls["conforme"] is True

    def test_classificacao_mantem_chaves_antigas(self):
        cls = classificar_oportunidade(_op("01. Suspect", tf=1))
        for chave in ("fase_analisada", "conforme", "problemas",
                      "problemas_rotulos", "regras_aplicaveis",
                      "temperatura_incoerente"):
            assert chave in cls
