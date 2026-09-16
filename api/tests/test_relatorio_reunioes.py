"""
HIPO - Testes puros do bloco de reunioes do fechamento.

A regra do desfecho mora em services/agenda.py e tem os testes dela; aqui
se confere que o fechamento USA essa regra, e nao uma copia.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services import relatorio_reunioes as rr

SP = ZoneInfo("America/Sao_Paulo")
DIA = datetime(2026, 9, 15, tzinfo=SP)
AGORA = datetime(2026, 9, 16, 6, 10, tzinfo=timezone.utc)  # 03:10 em SP


def _reuniao(hora=10, anfitriao="Bruno Gonçalo", **kw):
    prazo = DIA.replace(hour=hora)
    base = {
        "prazo": prazo, "duracao_min": 30, "desfecho": None,
        "concluida_em": None, "cancelada_em": None,
        "anfitriao": anfitriao, "anfitriao_cargo": "EV",
        "agendado_por": "Kethlleen Gomes", "empresa": "Metalurgica Andrade",
        "tipo_sigla": "DG", "tipo_nome": "Diagnóstico", "modalidade": "online",
    }
    base.update(kw)
    return base


class TestSituacao:
    def test_desfecho_registrado_ganha(self):
        assert rr.situacao(_reuniao(desfecho="no_show"), AGORA) == "no_show"

    def test_concluida_sem_desfecho_e_realizada(self):
        r = _reuniao(concluida_em=DIA.replace(hour=11))
        assert rr.situacao(r, AGORA) == "realizada"

    def test_cancelada_com_antecedencia_e_cancelada(self):
        r = _reuniao(cancelada_em=DIA.replace(hour=10) - timedelta(days=2))
        assert rr.situacao(r, AGORA) == "cancelada"

    def test_cancelada_em_cima_da_hora_e_no_show(self):
        r = _reuniao(cancelada_em=DIA.replace(hour=9))
        assert rr.situacao(r, AGORA) == "no_show"

    def test_passou_sem_ninguem_marcar_e_pendente(self):
        """Nada vira no-show sozinho -- mesma decisao da tela da Agenda."""
        assert rr.situacao(_reuniao(), AGORA) == "pendente"

    def test_ainda_nao_terminou_e_agendada(self):
        agora = DIA.replace(hour=10, minute=10)
        assert rr.situacao(_reuniao(hora=10), agora) == "agendada"


class TestMontar:
    def test_totais_e_por_anfitriao(self):
        r = rr.montar([
            _reuniao(hora=9, desfecho="realizada"),
            _reuniao(hora=10, desfecho="no_show"),
            _reuniao(hora=11, anfitriao="Jakeline Santana", desfecho="realizada"),
            _reuniao(hora=14, anfitriao="Jakeline Santana"),
        ], [], AGORA)
        assert (r["total"], r["realizadas"], r["no_show"], r["pendentes"]) == (4, 2, 1, 1)
        # Pendente fora do denominador: 2 de 3 com desfecho.
        assert r["taxa_realizacao_pct"] == 66.7
        bruno = next(p for p in r["por_anfitriao"] if p["nome"] == "Bruno Gonçalo")
        assert (bruno["total"], bruno["realizadas"], bruno["no_show"]) == (2, 1, 1)

    def test_itens_saem_na_hora_de_brasilia_e_em_ordem(self):
        r = rr.montar([_reuniao(hora=14), _reuniao(hora=9)], [], AGORA)
        assert [i["hora"] for i in r["itens"]] == ["09:00", "14:00"]
        assert r["itens"][0]["tipo"] == "DG · Diagnóstico"
        assert r["itens"][0]["situacao_rotulo"] == "Sem desfecho"

    def test_prazo_em_utc_vira_hora_local(self):
        """O asyncpg devolve timestamptz em UTC; a hora do e-mail e a local."""
        prazo = datetime(2026, 9, 15, 17, 0, tzinfo=timezone.utc)
        r = rr.montar([_reuniao(prazo=prazo)], [], AGORA)
        assert r["itens"][0]["hora"] == "14:00"

    def test_dia_sem_reuniao_tem_taxa_indefinida(self):
        r = rr.montar([], [], AGORA)
        assert r["total"] == 0
        assert r["taxa_realizacao_pct"] is None

    def test_agendamentos_por_quem_marcou(self):
        r = rr.montar([], [
            {"nome": "Gabriel Lira", "cargo": "SDR", "qtd": 1},
            {"nome": "Kethlleen Gomes", "cargo": "SDR", "qtd": 3},
            {"nome": None, "cargo": None, "qtd": 1},
        ], AGORA)
        assert r["agendamentos_total"] == 5
        assert [a["nome"] for a in r["agendamentos_por_pessoa"]] == [
            "Kethlleen Gomes", "(sem autor)", "Gabriel Lira",
        ]

    def test_sem_tipo_e_sem_empresa_nao_quebra(self):
        r = rr.montar([_reuniao(tipo_sigla=None, tipo_nome=None, empresa=None,
                                agendado_por=None, anfitriao=None)], [], AGORA)
        item = r["itens"][0]
        assert item["tipo"] == item["empresa"] == item["agendado_por"] == "—"
        assert item["anfitriao"] == "(sem anfitrião)"
